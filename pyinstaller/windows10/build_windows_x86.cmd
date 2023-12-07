@REM  build an x86 app

call conda create -y -n sanpy-pyinstaller-windows-x86 python=3.9

call conda activate sanpy-pyinstaller-windows-x86

@REM # conda env config vars set CONDA_SUBDIR=osx-64

@REM # conda deactivate
@REM # conda activate sanpy-pyinstaller-windows-x86

pip install --upgrade pip

pip install -e ../../.[gui]

pip install windows-curses

pip install pyinstaller

@REM # Possible do installation from requirements.txt

@REM # run pyinstaller to install at in the right directory
pyinstaller --noconfirm --clean pyinstaller-windows10.spec