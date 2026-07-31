"""
Optional UPnP port forwarding: SSDP discovery plus SOAP AddPortMapping.

Used only when the user ticks "Forward port automatically (UPnP)". Everything
here is best-effort and non-fatal: if it fails, the user is told and can forward
the port by hand. Nothing about the security of the session depends on UPnP - it
opens a path to a port that still demands a pinned certificate and an HMAC proof.

Two things make this module worth writing carefully anyway.

**A mapping must not outlive us.** A crash that leaves a permanent hole in the
user's router is a real harm we would have caused. Two independent defences:

1. Every mapping is created with a bounded lease (`NewLeaseDuration`), so the
   router expires it on its own. Some routers reject non-zero leases; only then
   do we fall back to a permanent mapping, and we record that we did.
2. `atexit` deletes any mapping still registered at interpreter shutdown, and
   `PortMapping` is a context manager for the normal path.

**An SSDP reply is unauthenticated input from the network.** Anything on the LAN
can answer a discovery multicast and claim to be a router, so every response is
treated as hostile until validated:

- The control URL must be HTTP(S) with a host that is a *private* IP address. A
  reply pointing at a public host would otherwise let a LAN attacker aim our
  SOAP requests (and our internal port number) at an arbitrary internet server.
- Response and XML sizes are capped before parsing.
- XML is parsed with `xml.etree.ElementTree`, which does not expand external
  entities, so a hostile device description cannot read our files.
- Timeouts are short and everything is bounded; a device that never answers
  costs a few seconds.

We use `urllib` from the standard library rather than a UPnP package, keeping
this dependency-free like the rest of the collab code.
"""

import atexit
import ipaddress
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree


SSDP_ADDRESS = '239.255.255.250'
SSDP_PORT = 1900

# The service types that expose port mapping, best first.
WAN_SERVICE_TYPES = (
    'urn:schemas-upnp-org:service:WANIPConnection:2',
    'urn:schemas-upnp-org:service:WANIPConnection:1',
    'urn:schemas-upnp-org:service:WANPPPConnection:1',
)

SSDP_SEARCH_TARGETS = (
    'urn:schemas-upnp-org:device:InternetGatewayDevice:1',
    'upnp:rootdevice',
)

# Mapping lease. Long enough not to interrupt a session, short enough that a
# crash-orphaned mapping disappears the same day.
DEFAULT_LEASE_SECONDS = 3600 * 8

# Renew before expiry so a long session is not cut off mid-edit.
RENEW_MARGIN_SECONDS = 300

DESCRIPTION_TIMEOUT = 5.0
SOAP_TIMEOUT = 8.0
SSDP_TIMEOUT = 3.0

MAX_SSDP_DATAGRAM = 4096
MAX_DESCRIPTION_BYTES = 512 * 1024
MAX_SOAP_RESPONSE_BYTES = 128 * 1024

MAPPING_DESCRIPTION = 'Reggie Next Collaboration'

# Carrier-grade NAT shared address space (RFC 6598). Python's `is_private` does
# NOT cover this range, so checking `is_private` alone would let us hand the
# user a WAN address that forwarding can never make reachable.
_CGNAT_NETWORK = ipaddress.ip_network('100.64.0.0/10')

_LOCATION_RE = re.compile(r'^location:\s*(.+)$', re.IGNORECASE | re.MULTILINE)


class UPnPError(Exception):
    """
    Raised when UPnP setup fails. Always non-fatal to the caller: report it and
    offer manual forwarding.
    """


# Mappings to clean up if the process exits without doing so itself.
_active_mappings = set()
_active_lock = threading.Lock()


def _register_active(mapping):
    with _active_lock:
        _active_mappings.add(mapping)


def _unregister_active(mapping):
    with _active_lock:
        _active_mappings.discard(mapping)


@atexit.register
def _cleanup_mappings():
    """
    Last-resort removal of mappings still open at interpreter shutdown.

    Silent by design: at exit there is nobody to tell, and a raised exception
    here would be noise on an otherwise clean quit.
    """
    with _active_lock:
        remaining = list(_active_mappings)
        _active_mappings.clear()

    for mapping in remaining:
        try:
            mapping.delete()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Address validation
# ---------------------------------------------------------------------------

def is_private_address(host):
    """
    Whether `host` is a literal private/loopback/link-local IP.

    Requiring a literal is deliberate: a hostname would need a DNS lookup whose
    answer an attacker on the LAN may control, and a real gateway always
    advertises itself by IP.
    """
    try:
        address = ipaddress.ip_address(str(host))
    except ValueError:
        return False

    return bool(address.is_private or address.is_loopback or address.is_link_local)


def validate_control_url(url):
    """
    Validates a control URL taken from an SSDP reply or a device description.

    Returns the normalised URL, or raises UPnPError. This is the gate that stops
    a hostile SSDP responder from redirecting our SOAP calls off the LAN.
    """
    try:
        parts = urllib.parse.urlsplit(str(url))
    except ValueError:
        raise UPnPError('router returned an unparsable control URL')

    if parts.scheme not in ('http', 'https'):
        raise UPnPError('router control URL uses an unsupported scheme %r' % parts.scheme)

    if not parts.hostname:
        raise UPnPError('router control URL has no host')

    if not is_private_address(parts.hostname):
        raise UPnPError(
            'refusing to talk to a UPnP device outside your local network (%s)'
            % parts.hostname)

    return urllib.parse.urlunsplit(parts)


# ---------------------------------------------------------------------------
# SSDP discovery
# ---------------------------------------------------------------------------

def discover_gateways(timeout=SSDP_TIMEOUT):
    """
    Multicasts M-SEARCH and returns validated device description URLs.

    Deduplicated, order preserved. An empty list means no gateway answered,
    which is normal on networks with UPnP disabled.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(0.5)

    locations = []

    try:
        for target in SSDP_SEARCH_TARGETS:
            request = (
                'M-SEARCH * HTTP/1.1\r\n'
                'HOST: %s:%d\r\n'
                'MAN: "ssdp:discover"\r\n'
                'MX: 2\r\n'
                'ST: %s\r\n'
                '\r\n'
            ) % (SSDP_ADDRESS, SSDP_PORT, target)

            try:
                sock.sendto(request.encode('ascii'), (SSDP_ADDRESS, SSDP_PORT))
            except OSError:
                continue

        deadline = time.monotonic() + float(timeout)

        while time.monotonic() < deadline:
            try:
                data, _sender = sock.recvfrom(MAX_SSDP_DATAGRAM)
            except socket.timeout:
                continue
            except OSError:
                break

            text = data.decode('utf-8', 'replace')
            match = _LOCATION_RE.search(text)
            if not match:
                continue

            try:
                location = validate_control_url(match.group(1).strip())
            except UPnPError:
                # A device claiming a non-local address: ignore it silently, it
                # is not something the user can act on.
                continue

            if location not in locations:
                locations.append(location)
    finally:
        try:
            sock.close()
        except OSError:
            pass

    return locations


# ---------------------------------------------------------------------------
# Device description
# ---------------------------------------------------------------------------

def _http_get(url, timeout, max_bytes):
    request = urllib.request.Request(url, method='GET')

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(max_bytes + 1)[:max_bytes]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UPnPError('could not read the router description: %s' % exc)


def _strip_namespace(tag):
    return tag.split('}', 1)[-1] if '}' in tag else tag


def find_wan_service(description_url):
    """
    Fetches a device description and returns (service_type, control_url) for the
    first WAN connection service it advertises.

    Raises UPnPError if the description is unreadable or has no such service.
    """
    body = _http_get(description_url, DESCRIPTION_TIMEOUT, MAX_DESCRIPTION_BYTES)

    try:
        # ElementTree does not resolve external entities, so a hostile
        # description cannot turn this into a file read.
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise UPnPError('router description is not valid XML: %s' % exc)

    services = {}

    for element in root.iter():
        if _strip_namespace(element.tag) != 'service':
            continue

        service_type = ''
        control_url = ''

        for child in element:
            name = _strip_namespace(child.tag)
            if name == 'serviceType':
                service_type = (child.text or '').strip()
            elif name == 'controlURL':
                control_url = (child.text or '').strip()

        if service_type and control_url:
            services[service_type] = control_url

    for service_type in WAN_SERVICE_TYPES:
        if service_type in services:
            absolute = urllib.parse.urljoin(description_url, services[service_type])
            return service_type, validate_control_url(absolute)

    raise UPnPError('the router does not offer UPnP port forwarding')


# ---------------------------------------------------------------------------
# SOAP
# ---------------------------------------------------------------------------

def _soap_escape(value):
    return (str(value)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def _soap_call(control_url, service_type, action, arguments):
    """
    Sends one SOAP action. Returns the response body as text.

    Argument values are XML-escaped, so a nickname or description containing
    '<' cannot break out of the envelope.
    """
    argument_xml = ''.join(
        '<%s>%s</%s>' % (name, _soap_escape(value), name)
        for name, value in arguments
    )

    envelope = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body>'
        '</s:Envelope>'
    ) % (action, service_type, argument_xml, action)

    body = envelope.encode('utf-8')

    request = urllib.request.Request(
        control_url,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'text/xml; charset="utf-8"',
            'SOAPAction': '"%s#%s"' % (service_type, action),
            'Content-Length': str(len(body)),
            'Connection': 'close',
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=SOAP_TIMEOUT) as response:
            return response.read(MAX_SOAP_RESPONSE_BYTES).decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        detail = exc.read(MAX_SOAP_RESPONSE_BYTES).decode('utf-8', 'replace')
        raise UPnPError('the router rejected %s: %s' % (action, _soap_error(detail) or exc))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UPnPError('could not reach the router: %s' % exc)


def _is_lease_rejection(error):
    """
    Whether a failed AddPortMapping was specifically about the lease duration.

    725 is OnlyPermanentLeasesSupported; 402 (InvalidArgs) shows up on firmware
    that will not accept NewLeaseDuration at all.
    """
    text = str(error)
    return ('725' in text
            or 'OnlyPermanentLeasesSupported' in text
            or '402' in text
            or 'InvalidArgs' in text)


def _soap_error(body):
    """
    Extracts a UPnP error code/description from a SOAP fault, for a message that
    tells the user something useful instead of just "500".
    """
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return ''

    code = ''
    description = ''

    for element in root.iter():
        name = _strip_namespace(element.tag)
        if name == 'errorCode':
            code = (element.text or '').strip()
        elif name == 'errorDescription':
            description = (element.text or '').strip()

    if code or description:
        return ('%s %s' % (code, description)).strip()

    return ''


# ---------------------------------------------------------------------------
# Port mapping
# ---------------------------------------------------------------------------

class PortMapping:
    """
    One TCP port mapping, removed on `delete()`, on context exit, or at
    interpreter shutdown - whichever happens first.

        with PortMapping.create(45923, internal_ip) as mapping:
            ...
    """

    def __init__(self, control_url, service_type, external_port, internal_port,
                 internal_ip, lease_seconds):
        self.control_url = control_url
        self.service_type = service_type
        self.external_port = int(external_port)
        self.internal_port = int(internal_port)
        self.internal_ip = internal_ip
        self.lease_seconds = int(lease_seconds)
        self.permanent = False       # True if the router refused a lease
        self.deleted = False

    # -- creation -----------------------------------------------------------

    @classmethod
    def create(cls, port, internal_ip, lease_seconds=DEFAULT_LEASE_SECONDS,
               description=MAPPING_DESCRIPTION, gateway_timeout=SSDP_TIMEOUT):
        """
        Discovers a gateway and maps `port` to `internal_ip`.

        Raises UPnPError if no gateway is found or the mapping is refused. The
        caller must treat that as "tell the user, carry on unforwarded".
        """
        if not is_private_address(internal_ip):
            raise UPnPError(
                'refusing to request a port mapping for %s, which is not a '
                'local address' % internal_ip)

        gateways = discover_gateways(timeout=gateway_timeout)
        if not gateways:
            raise UPnPError(
                'No UPnP router responded. You can still host by forwarding '
                'port %d to this computer manually.' % int(port))

        last_error = None

        for description_url in gateways:
            try:
                service_type, control_url = find_wan_service(description_url)
            except UPnPError as exc:
                last_error = exc
                continue

            mapping = cls(control_url, service_type, port, port,
                          internal_ip, lease_seconds)
            try:
                mapping._add(description)
            except UPnPError as exc:
                last_error = exc
                continue

            _register_active(mapping)
            return mapping

        raise UPnPError(str(last_error) if last_error
                        else 'no usable UPnP gateway was found')

    def _add(self, description):
        arguments = [
            ('NewRemoteHost', ''),
            ('NewExternalPort', self.external_port),
            ('NewProtocol', 'TCP'),
            ('NewInternalPort', self.internal_port),
            ('NewInternalClient', self.internal_ip),
            ('NewEnabled', '1'),
            ('NewPortMappingDescription', description),
            ('NewLeaseDuration', self.lease_seconds),
        ]

        try:
            _soap_call(self.control_url, self.service_type, 'AddPortMapping', arguments)
            return
        except UPnPError as exc:
            # Only retry when the router specifically objected to the lease
            # (725 OnlyPermanentLeasesSupported, or a bare 402 from firmware
            # that dislikes the argument). Any other error - a conflicting
            # mapping, an unauthorised request - is reported as-is, because
            # retrying it permanently would trade a clear failure for a mapping
            # that only atexit can clean up.
            if not _is_lease_rejection(exc):
                raise

        arguments[-1] = ('NewLeaseDuration', 0)
        _soap_call(self.control_url, self.service_type, 'AddPortMapping', arguments)
        self.permanent = True

    # -- removal ------------------------------------------------------------

    def delete(self):
        """
        Removes the mapping. Idempotent; never raises.

        Returns True if the router confirmed the removal. Failure is only worth
        a log line - the lease will expire, unless `permanent`, which is exactly
        why we avoid that path.
        """
        if self.deleted:
            return True

        self.deleted = True
        _unregister_active(self)

        try:
            _soap_call(self.control_url, self.service_type, 'DeletePortMapping', [
                ('NewRemoteHost', ''),
                ('NewExternalPort', self.external_port),
                ('NewProtocol', 'TCP'),
            ])
            return True
        except UPnPError:
            return False

    def renew(self, description=MAPPING_DESCRIPTION):
        """
        Re-adds the mapping to extend its lease. Returns True on success.
        """
        if self.deleted:
            return False

        try:
            self._add(description)
            return True
        except UPnPError:
            return False

    # -- context manager ----------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.delete()
        return False

    def __repr__(self):
        return '<PortMapping %s:%d -> %d%s>' % (
            self.internal_ip, self.internal_port, self.external_port,
            ' permanent' if self.permanent else '')


def external_ip_address(control_url, service_type):
    """
    Asks the router for its WAN address, so the host can show the address a
    remote peer needs. Returns '' if unavailable or not a usable public address.
    """
    try:
        body = _soap_call(control_url, service_type,
                          'GetExternalIPAddress', [])
    except UPnPError:
        return ''

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return ''

    for element in root.iter():
        if _strip_namespace(element.tag) == 'NewExternalIPAddress':
            text = (element.text or '').strip()
            try:
                address = ipaddress.ip_address(text)
            except ValueError:
                return ''

            # A private or CGNAT WAN address means the router is itself behind
            # another NAT: forwarding will not actually make the host reachable,
            # and returning nothing beats handing the user an address that
            # cannot work. (`is_private` alone misses 100.64/10.)
            if (address.is_private or address.is_loopback
                    or address in _CGNAT_NETWORK):
                return ''

            return text

    return ''
