# DISCLAIMER
- Program error reports tend to show the directory of the build location! So it will go `C:/Users/[yourname]/...` for example.

- Building on Mac and Linux hasn't been tested yet so it might not work on those platforms.

## Building Without Cython (Recommended)
Building without Cython will slow down the program a bit when it deals with anything LH related.

1. You need to have at least Python 3.10, so make sure to install it and add it to `PATH` on Windows.
1. Run the following command to install the required modules:
   ```
   pip install PyQt6 nsmblib pyinstaller
   ```
1. In `libs/__init__.py`, change the line `has_cython = True` to `has_cython = False`.
1. (Optional) You can change the version by editing the value of `PROJECT_VERSION` in the file `build_reggie.py` and the `ReggieVersionShort` value in the file `globals_.py`.
1. If you're on Windows, you can run the `build_reggie.bat` script. On other platforms, run the following command: `python -OO build_reggie.py`

After the script finishes, the executable can be found in the `distrib` folder.

## Building With Cython (Advanced)
Building with Cython will speed up the program a bit when it deals with anything LH related, but it's also more work to set up.

1. You need to use Python 3.10 or higher, so make sure to install it and add it to `PATH` on Windows.
1. Run this command to add the required modules:
   ```
   python -m pip install PyQt6 nsmblib Cython pyinstaller
   ```
1. In `libs/__init__.py`, remove the lines:
   ```
   import pyximport
   pyximport.install()
   ```

1. - On Windows: In the `libs` folder, run the `compile.bat` script.
   **NOTE:** The `compile.bat` script doesn't look for a specific Python version, so if nothing happens when ran, edit the script to use whichever version of Python you have with Cython installed.
   - On other OSes:
     1. Run this command in the `libs` folder directory:
        ```
        python compile.py build_ext --inplace
        ```
     1. Rename the created `.so` files in the new libs folder to correspond with their respective `.pyx` name (but don't change the extension).

1. Delete the `.pyx` files, and other files and folders that were created in the previous step.

1. - Windows: Download the Microsoft Build Tools 2015 installer from the following URL.
   http://download.microsoft.com/download/5/F/7/5F7ACAEB-8363-451F-9425-68A90F98B238/visualcppbuildtools_full.exe

   - On other OSes: Make sure you have a compatible C compiler with Cython (for example `gcc`). GCC is usually preinstalled on Linux, but if you don't have it, the command `sudo apt-get install build-essential` will fetch everything you need. On MacOSX, you can retrieve `gcc` by installing Apple’s XCode through running the command `xcode-select --install`.

1. (Optional) You can change the version by editing the value of `PROJECT_VERSION` in `build_reggie.py` and the `ReggieVersionShort` value in the file `globals_.py`.

1. - Windows: Run `build_reggie.bat`.
   - Other OSes: Run the following command in `build_reggie.py`'s directory:
     ```
     python -OO build_reggie.py
     ```

After the script finishes, the executable can be found in the `distrib` folder.