[app]
title = Лист
package.name = localoffice
package.domain = org.secure.office
version = 1.0.2
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt
icon.filename = app_icon.png
presplash.filename = app_icon.png
orientation = portrait
p4a.branch = v2024.01.21
# sqlite3 is included with Python; python-for-android supplies hostpython3.
# lxml 4.9.3 supports Python 3.11 and retains the static build env used by p4a.
requirements = python3,kivy==2.3.0,kivymd==1.2.0,python-docx,openpyxl,pypdf,lxml==4.9.3
# Files are selected through Android's system document picker (Storage Access Framework).
# It grants access only to files the user chooses; broad storage permissions are unnecessary.
android.api = 34
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
