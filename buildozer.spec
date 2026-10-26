[app]
# Название приложения на экране смартфона
title = Local Office

package.name = localoffice
package.domain = org.secure.office

# Версия приложения
version = 1.0.0

# Путь к папке проекта
source.dir = .

# Расширения файлов, которые упаковываются внутрь приложения
source.include_exts = py,png,jpg,kv,atlas,txt

# Ваша красивая иконка из папки проекта
icon.filename = app_icon.png

# Ориентация экрана
orientation = portrait

# ВАЖНО: Добавлены hostpython3, sqlite3, lxml для стабильной работы Word и сохранения согласий
requirements = python3,hostpython3,kivy==2.3.0,kivymd==1.2.0,python-docx,openpyxl,pypdf,lxml,sqlite3

# Разрешения на доступ к хранилищу (Интернет полностью вырезан!)
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

# Требования RuStore (Target API 34, Android 14)
android.api = 34
android.minapi = 21

# ВАЖНО: Оставили arm64-v8a для ускорения компиляции. Для релиза добавите через запятую armeabi-v7a
android.archs = arm64-v8a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
