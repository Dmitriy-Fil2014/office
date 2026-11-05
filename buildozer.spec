[app]
title = Лист
package.name = localoffice
package.domain = org.secure.office
version = 1.0.2
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt
icon.filename = app_icon.png
presplash.filename = splash_leaf.jpg
android.presplash_color = #00180C
# Show the supplied static Leaf artwork immediately during native Android startup.
orientation = portrait
p4a.branch = v2024.01.21
# sqlite3 is included with Python; python-for-android supplies hostpython3.
# lxml 4.9.3 supports Python 3.11 and retains the static build env used by p4a.
requirements = python3,kivy==2.3.0,kivymd==1.2.0,python-docx,openpyxl,pypdf,python-pptx,lxml==4.9.3,typing_extensions==4.12.2,pillow==10.4.0
# The app requests Android's special all-files access for its on-device document list.
android.manifest.intent_filters = ./intent_filters.xml
# MANAGE_EXTERNAL_STORAGE requires the user to approve access in Android Settings.
android.release_artifact = apk
android.api = 34
android.minapi = 21
android.permissions = MANAGE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
