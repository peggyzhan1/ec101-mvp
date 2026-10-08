python -m pip install -r desktop/requirements-build.txt
pyinstaller --noconfirm --windowed --name EC101-Converter --paths src desktop/app.py
