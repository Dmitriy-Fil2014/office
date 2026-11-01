from kivy.utils import platform
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
import traceback
import locale
import sys
import os
import io
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image as KivyImage
import io
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image as KivyImage
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDFillRoundFlatButton

if platform == "android":
    from jnius import autoclass
    from android import activity


class DocumentLocalApp(MDApp):
    dialog = None
    consent_dialog = None
    current_uri = None
    current_file_name = ""
    current_file_format = ""
    current_file_bytes = b""
    pending_create_bytes = b""

    def build(self):
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.accent_palette = "LightBlue"
        self.config.setdefaults("General", {"accepted_legal": "0", "theme_mode": "system", "language": "ru"})
        try:
            return Builder.load_file("app.kv")
        except Exception as exc:
            self._write_startup_error("Ошибка загрузки интерфейса")
            # Keep the process alive and show a readable diagnostic instead
            # of leaving the user with a black screen and an immediate exit.
            return Label(
                text=(
                    "Лист: не удалось загрузить интерфейс.\\n"
                    "Ошибка записана в local_office_startup.log\\n\\n"
                    + str(exc)
                ),
                halign="center",
                valign="middle",
            )

    def on_start(self):
        self._install_exception_hook()
        try:
            self.apply_preferences()
        except Exception:
            self._write_startup_error("Ошибка применения настроек при запуске")
        # Request Android storage access as soon as the first screen is ready.
        Clock.schedule_once(self._finish_startup, 0.65)
        Clock.schedule_once(self._animate_splash_loading, 0.1)
        Clock.schedule_once(self._hide_splash, 2.0)
        Clock.schedule_once(self.request_all_files_access, 0.85)
        Clock.schedule_once(self._open_shared_file, 1.0)
        Clock.schedule_once(lambda _dt: self.refresh_document_list(), 1.2)

    def request_all_files_access(self, *_):
        if platform != "android":
            return
        try:
            BuildVersion = autoclass("android.os.Build$VERSION")
            current = autoclass("org.kivy.android.PythonActivity").mActivity
            if int(BuildVersion.SDK_INT) >= 30:
                Environment = autoclass("android.os.Environment")
                if not Environment.isExternalStorageManager():
                    Intent = autoclass("android.content.Intent")
                    Uri = autoclass("android.net.Uri")
                    intent = Intent("android.settings.MANAGE_APP_ALL_FILES_ACCESS_PERMISSION")
                    intent.setData(Uri.parse("package:" + str(current.getPackageName())))
                    current.startActivityForResult(intent, 1016)
                else:
                    Clock.schedule_once(lambda _dt: self.refresh_document_list(), 0.2)
            else:
                permissions = ["android.permission.READ_EXTERNAL_STORAGE",
                               "android.permission.WRITE_EXTERNAL_STORAGE"]
                current.requestPermissions(permissions, 1017)
        except Exception as exc:
            self.root.ids.status_label.text = "Не удалось запросить доступ к хранилищу: " + str(exc)

    def on_resume(self):
        try:
            Clock.schedule_once(lambda _dt: self.refresh_document_list(), 0.5)
        except Exception:
            pass

    def refresh_document_list(self):
        try:
            container = self.root.ids.documents_list
            container.clear_widgets()
            if platform != "android":
                container.add_widget(MDLabel(text="Документы появятся здесь после предоставления доступа к хранилищу.",
                                             size_hint_y=None, height="48dp"))
                return
            BuildVersion = autoclass("android.os.Build$VERSION")
            if int(BuildVersion.SDK_INT) >= 30:
                Environment = autoclass("android.os.Environment")
                if not Environment.isExternalStorageManager():
                    container.add_widget(MDLabel(text="Разрешите доступ ко всем файлам в настройках Android.",
                                                 size_hint_y=None, height="48dp"))
                    return
            root_path = str(autoclass("android.os.Environment").getExternalStorageDirectory().getAbsolutePath())
            allowed = (".docx", ".xlsx", ".pptx", ".pdf", ".txt")
            found = []
            for base, dirs, files in os.walk(root_path):
                dirs[:] = [d for d in dirs if d not in ("Android", ".thumbnails")]
                for filename in files:
                    if filename.lower().endswith(allowed):
                        path = os.path.join(base, filename)
                        found.append(path)
                if len(found) >= 500:
                    break
            found.sort(key=lambda p: os.path.basename(p).lower())
            for path in found:
                name = os.path.basename(path)
                button = MDFillRoundFlatButton(
                    text=name, size_hint_x=1,
                    on_release=lambda *_ , selected=path: self.open_local_document(selected))
                container.add_widget(button)
            if not found:
                container.add_widget(MDLabel(text="Документы не найдены. Поддерживаются DOCX, XLSX, PPTX, PDF и TXT.",
                                             size_hint_y=None, height="56dp"))
            self.root.ids.status_label.text = "Документов найдено: " + str(len(found))
        except Exception as exc:
            try:
                self.root.ids.status_label.text = "Не удалось загрузить список документов: " + str(exc)
            except Exception:
                pass

    def open_local_document(self, path):
        try:
            processor = self._get_processor()
            with open(path, "rb") as stream:
                data = stream.read()
            self.current_local_path = path
            self.current_uri = None
            self.current_file_name = os.path.basename(path)
            self.current_file_bytes = data
            self.current_file_format = processor.detect_format(self.current_file_name, "", data)
            if self.current_file_format == "xlsx":
                self.show_spreadsheet_editor()
            elif self.current_file_format == "docx":
                self.show_word_editor()
            elif self.current_file_format == "pptx":
                self.root.ids.file_content_view.text = processor.read_pptx_bytes(data)
                self.show_presentation_editor()
            else:
                readers = {"txt": processor.read_txt_bytes, "pdf": processor.read_pdf_bytes}
                self.root.ids.file_content_view.text = readers[self.current_file_format](data)
                self.show_fullscreen_text_editor(self.root.ids.file_content_view.text)
            self.root.ids.save_btn.disabled = False
            self.root.ids.status_label.text = "Открыт документ: " + self.current_file_name
        except Exception as exc:
            self.root.ids.status_label.text = "Ошибка открытия документа: " + str(exc)

    def _open_shared_file(self, _dt):
        if platform != "android":
            return
        try:
            current = autoclass("org.kivy.android.PythonActivity").mActivity
            incoming = current.getIntent()
            Intent = autoclass("android.content.Intent")
            if incoming.getAction() in (Intent.ACTION_VIEW, Intent.ACTION_EDIT):
                uri = incoming.getData()
                if uri is not None:
                    self.current_uri = uri
                    self.process_android_uri(uri)
        except Exception as exc:
            self.root.ids.status_label.text = "Не удалось принять файл из другого приложения: " + str(exc)

    def _animate_splash_loading(self, _dt):
        try:
            label = self.root.ids.splash_loading_label
            pulse = Animation(opacity=0.35, duration=0.65, t="in_out_sine") + Animation(opacity=1, duration=0.65, t="in_out_sine")
            pulse.repeat = True
            self.splash_pulse = pulse
            pulse.start(label)
        except Exception:
            pass

    def _hide_splash(self, _dt):
        try:
            pulse = getattr(self, "splash_pulse", None)
            if pulse:
                pulse.cancel(self.root.ids.splash_loading_label)
            layer = self.root.ids.splash_layer
            animation = Animation(opacity=0, duration=0.28, t="out_quad")
            def remove_splash(*_):
                parent = layer.parent
                if parent is not None:
                    parent.remove_widget(layer)
            animation.bind(on_complete=remove_splash)
            animation.start(layer)
        except Exception:
            pass

    def _install_exception_hook(self):
        if getattr(self, "_exception_hook_installed", False):
            return
        self._exception_hook_installed = True
        previous_hook = sys.excepthook

        def report_uncaught_exception(exc_type, exc_value, exc_traceback):
            try:
                with open(self._diagnostic_log_path(), "a", encoding="utf-8") as log:
                    log.write("\n=== НЕОБРАБОТАННАЯ ОШИБКА PYTHON ===\n")
                    traceback.print_exception(exc_type, exc_value, exc_traceback, file=log)
            except Exception:
                pass
            previous_hook(exc_type, exc_value, exc_traceback)

        sys.excepthook = report_uncaught_exception

    def _diagnostic_log_path(self):
        try:
            return os.path.join(self.user_data_dir, "local_office_startup.log")
        except Exception:
            return "local_office_startup.log"

    def _get_processor(self):
        from document_core import DocumentProcessor
        return DocumentProcessor

    def _system_theme(self):
        if platform == "android":
            try:
                Configuration = autoclass("android.content.res.Configuration")
                act = autoclass("org.kivy.android.PythonActivity").mActivity
                mode = act.getResources().getConfiguration().uiMode
                return "Dark" if (mode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES else "Light"
            except Exception:
                pass
        return "Light"

    def _system_language(self):
        try:
            return "en" if (locale.getlocale()[0] or "ru").lower().startswith("en") else "ru"
        except Exception:
            return "ru"

    def apply_preferences(self):
        mode = self.config.get("General", "theme_mode")
        self.theme_cls.theme_style = self._system_theme() if mode == "system" else ("Dark" if mode == "dark" else "Light")
        lang = self.config.get("General", "language")
        # Russian is the fixed first-run default on every device.
        if lang not in ("ru", "en"):
            lang = "ru"
            self.config.set("General", "language", "ru")
            self.config.write()
        self.language = lang
        self._refresh_language()

    def _refresh_language(self):
        en = getattr(self, "language", "ru") == "en"
        try:
            self.root.ids.app_title.title = "Leaf" if en else "Лист"
            self.root.ids.workspace_title.text = "Your workspace" if en else "Ваше рабочее пространство"
            self.root.ids.editor_title.text = "Document editor" if en else "Редактор документов"
            self.root.ids.status_label.text = "Choose a file or create a new document." if en else "Откройте файл или создайте новый документ."
            self.root.ids.create_btn.text = "Create" if en else "Создать"
            self.root.ids.open_btn.text = "Open file" if en else "Открыть файл"
            self.root.ids.save_btn.text = "Save" if en else "Сохранить"
            self.root.ids.file_content_view.hint_text = "Document text will appear here" if en else "Здесь появится текст документа"
        except Exception:
            pass

    def set_theme_mode(self, mode):
        self.config.set("General", "theme_mode", mode)
        self.config.write()
        self.apply_preferences()
        if self.dialog: self.dialog.dismiss()

    def set_language(self, language):
        self.config.set("General", "language", language)
        self.config.write()
        self.apply_preferences()
        if self.dialog: self.dialog.dismiss()

    def show_settings_menu(self):
        en = getattr(self, "language", "ru") == "en"
        modal = ModalView(size_hint=(0.94, 0.94), auto_dismiss=True,
                          background_color=(0.02, 0.05, 0.12, 0.62))
        card = MDCard(orientation="vertical", padding="18dp", spacing="8dp",
                      radius=[24, 24, 24, 24], elevation=8,
                      md_bg_color=(0.97, 0.98, 1, 1) if self.theme_cls.theme_style == "Light" else (0.10, 0.13, 0.20, 1))
        card.add_widget(MDLabel(text="Настройки" if not en else "Settings",
                                font_style="H6", bold=True, size_hint_y=None, height="42dp"))
        card.add_widget(MDLabel(text="Тема оформления" if not en else "Appearance",
                                size_hint_y=None, height="26dp", theme_text_color="Secondary"))
        for label, mode in ([("Системная", "system"), ("Светлая", "light"), ("Тёмная", "dark")] if not en else [("System", "system"), ("Light", "light"), ("Dark", "dark")]):
            card.add_widget(MDFillRoundFlatButton(text=label, size_hint_x=1,
                on_release=lambda *_, value=mode: (modal.dismiss(), self.set_theme_mode(value))))
        card.add_widget(MDLabel(text="Документы и соглашения" if not en else "Documents & legal",
                                size_hint_y=None, height="26dp", theme_text_color="Secondary"))
        card.add_widget(MDFillRoundFlatButton(
            text="Политика конфиденциальности" if not en else "Privacy policy",
            size_hint_x=1, on_release=lambda *_: self.show_legal_doc(
                "privacy_policy.txt", "Политика конфиденциальности" if not en else "Privacy Policy")))
        card.add_widget(MDFillRoundFlatButton(
            text="Условия использования" if not en else "Terms of use",
            size_hint_x=1, on_release=lambda *_: self.show_legal_doc(
                "terms_of_use.txt", "Условия использования" if not en else "Terms of Use")))
        card.add_widget(MDLabel(text="Язык" if not en else "Language",
                                size_hint_y=None, height="26dp", theme_text_color="Secondary"))
        card.add_widget(MDFillRoundFlatButton(text="Русский", size_hint_x=1,
            on_release=lambda *_: (modal.dismiss(), self.set_language("ru"))))
        card.add_widget(MDFillRoundFlatButton(text="English", size_hint_x=1,
            on_release=lambda *_: (modal.dismiss(), self.set_language("en"))))
        modal.add_widget(card)
        self.settings_view = modal
        modal.open()

    def _write_startup_error(self, title):
        try:
            with open(self._diagnostic_log_path(), "a", encoding="utf-8") as log:
                log.write("\n=== " + title + " ===\n")
                log.write(traceback.format_exc())
        except Exception:
            pass

    def _finish_startup(self, _dt):
        try:
            if self.config.get("General", "accepted_legal") == "0":
                self.show_mandatory_consent_dialog()
        except Exception as exc:
            self._write_startup_error("Ошибка первого запуска")
            try:
                self.root.ids.status_label.text = (
                    "Не удалось открыть окно приветствия. "
                    "Приложение продолжит работу. " + str(exc)
                )
            except Exception:
                pass

    def show_mandatory_consent_dialog(self):
        en = getattr(self, "language", "ru") == "en"
        modal = ModalView(size_hint=(0.92, 0.80), auto_dismiss=False,
                          background_color=(0.02, 0.05, 0.12, 0.65))
        card = MDCard(orientation="vertical", padding="18dp", spacing="10dp",
                      radius=[24, 24, 24, 24], elevation=8,
                      md_bg_color=self.theme_cls.bg_normal)
        card.add_widget(MDLabel(text="Welcome to Leaf" if en else "Добро пожаловать в «Лист»",
                                font_style="H6", bold=True, size_hint_y=None, height="44dp"))
        scroll = ScrollView(do_scroll_x=False)
        intro = MDLabel(text=("Select a document to open it. Files are processed on your device."
                              if en else "Выберите документ, чтобы открыть его. Файлы обрабатываются на вашем устройстве."),
                        size_hint_y=None, halign="left", valign="top")
        intro.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        intro.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + 12))
        scroll.add_widget(intro)
        card.add_widget(scroll)
        card.add_widget(MDFillRoundFlatButton(
            text="Прочитать политику конфиденциальности" if not en else "Read privacy policy",
            size_hint_x=1, on_release=lambda *_: self.show_legal_doc(
                "privacy_policy.txt", "Политика конфиденциальности" if not en else "Privacy Policy")))
        card.add_widget(MDFillRoundFlatButton(
            text="Прочитать условия использования" if not en else "Read terms of use",
            size_hint_x=1, on_release=lambda *_: self.show_legal_doc(
                "terms_of_use.txt", "Условия использования" if not en else "Terms of Use")))
        card.add_widget(MDLabel(
            text=("Ознакомьтесь с обоими документами перед согласием."
                  if not en else "Please review both documents before accepting."),
            theme_text_color="Secondary", size_hint_y=None, height="36dp"))
        card.add_widget(MDFillRoundFlatButton(text="I AGREE" if en else "СОГЛАСЕН",
            size_hint_x=1, on_release=self.accept_legal_agreements))
        modal.add_widget(card)
        self.consent_dialog = modal
        modal.open()

    def view_doc_from_consent(self, filename, title_text):
        self.show_legal_doc(filename, title_text)

    def accept_legal_agreements(self, instance):
        self.config.set("General", "accepted_legal", "1")
        self.config.write()
        if self.consent_dialog:
            self.consent_dialog.dismiss()

    def show_new_document_menu(self):
        en = getattr(self, "language", "ru") == "en"
        modal = ModalView(size_hint=(0.88, 0.72), auto_dismiss=True,
                          background_color=(0.02, 0.05, 0.12, 0.62))
        card = MDCard(orientation="vertical", padding="18dp", spacing="10dp",
                      radius=[24, 24, 24, 24], elevation=8,
                      md_bg_color=self.theme_cls.bg_normal)
        card.add_widget(MDLabel(text="Create a document" if en else "Создать документ",
                                font_style="H6", bold=True, size_hint_y=None, height="42dp"))
        for label, fmt in [("Word (.docx)", "docx"), ("Excel (.xlsx)", "xlsx"),
                           ("PowerPoint (.pptx)", "pptx"), ("Text (.txt)", "txt")]:
            card.add_widget(MDFillRoundFlatButton(text=label, size_hint_x=1,
                on_release=lambda *_ , value=fmt: (modal.dismiss(), self.create_new_document(value))))
        modal.add_widget(card)
        self.create_menu = modal
        modal.open()

    def create_new_document(self, file_format):
        try:
            if self.dialog:
                self.dialog.dismiss()
            processor = self._get_processor()
            self.current_file_format = file_format
            self.current_file_name = {
                "docx": "Новый документ.docx",
                "xlsx": "Новая таблица.xlsx",
                "pptx": "Новая презентация.pptx",
                "txt": "Новый файл.txt",
            }[file_format]
            self.current_file_bytes = processor.create_document_bytes(file_format)
            if file_format == "pptx":
                self.root.ids.file_content_view.text = processor.read_pptx_bytes(self.current_file_bytes)
            self.current_uri = None
            self.current_local_path = None
            self.root.ids.file_content_view.text = "[Слайд 1]\nВведите текст слайда" if file_format == "pptx" else ""
            if file_format == "xlsx":
                self.show_spreadsheet_editor()
            elif file_format == "docx":
                self.show_word_editor()
            elif file_format == "pptx":
                self.show_presentation_editor()
            else:
                self.show_fullscreen_text_editor("")
            self.root.ids.save_btn.disabled = False
            self.root.ids.status_label.text = "Новый файл. Нажмите «Сохранить» и выберите место."
        except Exception as exc:
            self.root.ids.status_label.text = f"Не удалось создать файл: {exc}"

    def _start_create_document(self):
        try:
            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            mime = {
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "txt": "text/plain",
            }[self.current_file_format]
            intent.setType(mime)
            intent.putExtra(Intent.EXTRA_TITLE, self.current_file_name)
            activity.bind(on_activity_result=self.on_file_selected)
            current = autoclass("org.kivy.android.PythonActivity").mActivity
            current.startActivityForResult(intent, 1013)
        except Exception as exc:
            self.root.ids.status_label.text = f"Не удалось создать файл: {exc}"

    def _write_new_document(self):
        try:
            resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
            stream = resolver.openOutputStream(self.current_uri, "wt")
            if stream is None:
                raise IOError("Android не смог создать файл.")
            try:
                stream.write(self.pending_create_bytes)
                stream.flush()
            finally:
                stream.close()
            self.current_file_bytes = self.pending_create_bytes
            self.root.ids.status_label.text = f"Файл {self.current_file_name} создан."
        except Exception as exc:
            self.root.ids.status_label.text = f"Ошибка создания файла: {exc}"

    def open_system_storage(self):
        if platform != "android":
            self.root.ids.status_label.text = "Откройте APK на Android для выбора файла."
            return

        try:
            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            )
            intent.setType("*/*")
            mime_types = [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/pdf",
                "text/plain",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ]
            intent.putExtra(Intent.EXTRA_MIME_TYPES, mime_types)
            activity.bind(on_activity_result=self.on_file_selected)
            current_activity = autoclass(
                "org.kivy.android.PythonActivity"
            ).mActivity
            current_activity.startActivityForResult(intent, 1012)
        except Exception as exc:
            self._write_startup_error("Ошибка выбора файла")
            self.root.ids.status_label.text = f"Не удалось открыть выбор файла: {exc}"

    def on_file_selected(self, request_code, result_code, intent):
        if request_code not in (1012, 1013, 1015, 1016):
            return
        activity.unbind(on_activity_result=self.on_file_selected)
        Activity = autoclass("android.app.Activity")
        if request_code == 1016:
            Clock.schedule_once(lambda _dt: self.refresh_document_list(), 0.6)
            return
        if result_code == Activity.RESULT_OK and intent is not None:
            self.current_uri = intent.getData()
            if request_code == 1015:
                self.tree_uri = self.current_uri
                try:
                    Intent = autoclass("android.content.Intent")
                    flags = intent.getFlags() & (
                        Intent.FLAG_GRANT_READ_URI_PERMISSION
                        | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                    )
                    autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver().takePersistableUriPermission(
                        self.tree_uri, flags)
                except Exception:
                    pass
                self.show_folder_contents(self.tree_uri)
                return
            if request_code == 1013:
                self._write_new_document()
                return
            if self.current_uri is not None:
                # Android's system document picker grants access to the
                # selected file; broad storage permission is not required.
                try:
                    Intent = autoclass("android.content.Intent")
                    flags = intent.getFlags() & (
                        Intent.FLAG_GRANT_READ_URI_PERMISSION
                        | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                    )
                    current_activity = autoclass(
                        "org.kivy.android.PythonActivity"
                    ).mActivity
                    current_activity.getContentResolver().takePersistableUriPermission(
                        self.current_uri, flags
                    )
                except Exception:
                    pass
                self.process_android_uri(self.current_uri)

    def request_folder_access(self):
        if platform != "android":
            self.root.ids.status_label.text = "Выбор папки доступен в Android-приложении."
            return
        try:
            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            intent.addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
            )
            activity.bind(on_activity_result=self.on_file_selected)
            autoclass("org.kivy.android.PythonActivity").mActivity.startActivityForResult(
                intent, 1015)
            self.root.ids.status_label.text = "Выберите папку и подтвердите доступ кнопкой «Использовать эту папку»."
        except Exception as exc:
            self.root.ids.status_label.text = "Не удалось запросить доступ к папке: " + str(exc)

    def show_folder_contents(self, tree_uri, parent_document_id=None):
        try:
            Documents = autoclass("android.provider.DocumentsContract")
            Document = autoclass("android.provider.DocumentsContract$Document")
            resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
            if parent_document_id is None:
                parent_document_id = Documents.getTreeDocumentId(tree_uri)
            children_uri = Documents.buildChildDocumentsUriUsingTree(
                tree_uri, parent_document_id)
            cursor = resolver.query(children_uri, None, None, None, None)
            modal = ModalView(size_hint=(0.94, 0.90), auto_dismiss=True)
            outer = MDBoxLayout(orientation="vertical", padding="12dp", spacing="8dp")
            outer.add_widget(MDLabel(text="Файлы и папки", size_hint_y=None,
                                     height="42dp", bold=True))
            scroll = ScrollView()
            listing = MDBoxLayout(orientation="vertical", size_hint_y=None, spacing="6dp")
            listing.bind(minimum_height=listing.setter("height"))
            if cursor is not None:
                try:
                    id_col = cursor.getColumnIndex(Document.COLUMN_DOCUMENT_ID)
                    name_col = cursor.getColumnIndex(Document.COLUMN_DISPLAY_NAME)
                    mime_col = cursor.getColumnIndex(Document.COLUMN_MIME_TYPE)
                    while cursor.moveToNext():
                        document_id = str(cursor.getString(id_col))
                        name = str(cursor.getString(name_col) or "Без названия")
                        mime = str(cursor.getString(mime_col) or "")
                        is_dir = mime == Document.MIME_TYPE_DIR
                        button = MDFillRoundFlatButton(
                            text=("📁 " if is_dir else "📄 ") + name,
                            size_hint_x=1,
                            on_release=lambda *_ , did=document_id, directory=is_dir:
                                (modal.dismiss(),
                                 self.show_folder_contents(tree_uri, did) if directory else
                                 self.process_android_uri(Documents.buildDocumentUriUsingTree(tree_uri, did))))
                        listing.add_widget(button)
                finally:
                    cursor.close()
            scroll.add_widget(listing)
            outer.add_widget(scroll)
            outer.add_widget(MDFillRoundFlatButton(
                text="Закрыть", size_hint_x=1,
                on_release=lambda *_: modal.dismiss()))
            modal.add_widget(outer)
            self.folder_view = modal
            modal.open()
            self.root.ids.status_label.text = "Папка открыта. Выберите документ из списка."
        except Exception as exc:
            self.root.ids.status_label.text = "Не удалось показать содержимое папки: " + str(exc)

    def _get_file_metadata(self, uri, resolver):
        name = ""
        mime_type = resolver.getType(uri) or ""
        cursor = None
        try:
            OpenableColumns = autoclass("android.provider.OpenableColumns")
            cursor = resolver.query(uri, None, None, None, None)
            if cursor is not None:
                name_index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if name_index >= 0 and cursor.moveToFirst():
                    name = str(cursor.getString(name_index) or "")
        finally:
            if cursor is not None:
                cursor.close()
        if not name:
            name = str(uri.getLastPathSegment() or "document")
        return name, mime_type

    def _read_android_stream(self, input_stream):
        Byte = autoclass("java.lang.Byte")
        Array = autoclass("java.lang.reflect.Array")
        buffer = Array.newInstance(Byte.TYPE, 8192)
        chunks = bytearray()
        try:
            while True:
                count = input_stream.read(buffer)
                if count == -1:
                    break
                if count > 0:
                    chunks.extend((int(buffer[i]) & 255) for i in range(count))
        finally:
            input_stream.close()
        return bytes(chunks)

    def process_android_uri(self, uri):
        try:
            current_activity = autoclass("org.kivy.android.PythonActivity").mActivity
            resolver = current_activity.getContentResolver()
            self.current_local_path = None
            self.current_file_name, mime_type = self._get_file_metadata(uri, resolver)
            input_stream = resolver.openInputStream(uri)
            if input_stream is None:
                raise IOError("Android не смог открыть выбранный файл.")
            self.current_file_bytes = self._read_android_stream(input_stream)
            DocumentProcessor = self._get_processor()
            self.current_file_format = DocumentProcessor.detect_format(
                self.current_file_name, mime_type, self.current_file_bytes
            )
            if self.current_file_format == "xlsx":
                self.show_spreadsheet_editor()
                self.root.ids.status_label.text = "Открыта таблица: " + self.current_file_name
                return
            if self.current_file_format == "docx":
                self.show_word_editor()
                self.root.ids.status_label.text = "Открыт документ Word: " + self.current_file_name
                return
            if self.current_file_format == "pptx":
                self.root.ids.file_content_view.text = DocumentProcessor.read_pptx_bytes(self.current_file_bytes)
                self.show_presentation_editor()
                self.root.ids.status_label.text = "Открыта презентация: " + self.current_file_name
                return

            readers = {"txt": DocumentProcessor.read_txt_bytes, "pdf": DocumentProcessor.read_pdf_bytes}
            text = readers[self.current_file_format](self.current_file_bytes)
            self.root.ids.file_content_view.text = text
            self.root.ids.save_btn.disabled = False
            self.show_fullscreen_text_editor(text)
            self.root.ids.status_label.text = (
                f"Открыт {self.current_file_name}. "
                "Редактирование выполняется локально."
            )
        except Exception as exc:
            self._write_startup_error("Ошибка чтения документа")
            self.root.ids.file_content_view.text = ""
            self.root.ids.save_btn.disabled = True
            self.root.ids.status_label.text = f"Ошибка открытия: {exc}"


    def show_spreadsheet_editor(self):
        values = self._get_processor().read_excel_grid(self.current_file_bytes)
        self.spreadsheet_cells = []
        modal = ModalView(size_hint=(1, 1), auto_dismiss=False)
        outer = MDBoxLayout(orientation="vertical", padding="10dp", spacing="8dp")
        outer.add_widget(MDLabel(text="Таблица Excel", size_hint_y=None, height="42dp", bold=True, halign="center"))
        scroll = ScrollView(do_scroll_x=True, do_scroll_y=True)
        grid = GridLayout(cols=max(8, max((len(row) for row in values), default=8)), size_hint=(None, None), spacing="2dp",
                          row_default_height="42dp", row_force_default=True)
        grid.bind(minimum_width=grid.setter("width"), minimum_height=grid.setter("height"))
        for row in values:
            cells = []
            for value in row:
                field = TextInput(text="" if value is None else str(value), multiline=False,
                                  size_hint=(None, None), size=("112dp", "42dp"),
                                  font_size="14sp", background_color=(0.94, 0.97, 1, 1),
                                  foreground_color=(0.08, 0.14, 0.24, 1))
                grid.add_widget(field)
                cells.append(field)
            while len(cells) < 8:
                field = TextInput(multiline=False, size_hint=(None, None),
                                  size=("112dp", "42dp"), font_size="14sp")
                grid.add_widget(field)
                cells.append(field)
            self.spreadsheet_cells.append(cells)
        scroll.add_widget(grid)
        outer.add_widget(scroll)
        self.spreadsheet_grid = grid
        actions = MDBoxLayout(size_hint_y=None, height="50dp", spacing="5dp")
        actions.add_widget(MDFillRoundFlatButton(text="+ Строка", on_release=lambda *_: self.add_spreadsheet_row()))
        actions.add_widget(MDFillRoundFlatButton(text="+ Столбец", on_release=lambda *_: self.add_spreadsheet_column()))
        actions.add_widget(MDFillRoundFlatButton(text="Сохранить", on_release=lambda *_: (modal.dismiss(), self.save_changes_to_storage())))
        actions.add_widget(MDFillRoundFlatButton(text="Закрыть", on_release=lambda *_: modal.dismiss()))
        outer.add_widget(actions)
        modal.add_widget(outer)
        self.spreadsheet_view = modal
        modal.open()

    def add_spreadsheet_row(self):
        grid = getattr(self, "spreadsheet_grid", None)
        cells = getattr(self, "spreadsheet_cells", None)
        if grid is None or cells is None:
            return
        if len(cells) >= 500:
            self.root.ids.status_label.text = "Достигнут лимит: 500 строк."
            return
        row = []
        for _ in range(grid.cols):
            field = TextInput(multiline=False, size_hint=(None, None),
                              size=("112dp", "42dp"), font_size="14sp")
            grid.add_widget(field)
            row.append(field)
        cells.append(row)

    def add_spreadsheet_column(self):
        grid = getattr(self, "spreadsheet_grid", None)
        cells = getattr(self, "spreadsheet_cells", None)
        if grid is None or cells is None or grid.cols >= 50:
            return
        for row in cells:
            field = TextInput(multiline=False, size_hint=(None, None),
                              size=("112dp", "42dp"), font_size="14sp")
            grid.add_widget(field)
            row.append(field)
        grid.cols += 1

    def add_table_to_word(self):
        if self.current_file_format != "docx":
            self.root.ids.status_label.text = "Сначала откройте документ Word (.docx)."
            return
        modal = ModalView(size_hint=(0.92, 0.82), auto_dismiss=True)
        outer = MDBoxLayout(orientation="vertical", padding="12dp", spacing="8dp")
        outer.add_widget(MDLabel(text="Вставить таблицу — выберите размер",
                                 size_hint_y=None, height="42dp", halign="center", bold=True))
        outer.add_widget(MDLabel(text="Нажмите на квадратик в нужном столбце и строке",
                                 size_hint_y=None, height="34dp", halign="center",
                                 theme_text_color="Secondary"))
        grid = GridLayout(cols=8, spacing="3dp", size_hint=(1, 1))
        for r in range(1, 9):
            for c in range(1, 9):
                cell = MDFillRoundFlatButton(
                    text="□", size_hint=(1, 1),
                    on_release=lambda *_ , rows=r, cols=c:
                        self._insert_word_table(rows, cols, modal))
                grid.add_widget(cell)
        outer.add_widget(grid)
        outer.add_widget(MDFillRoundFlatButton(
            text="Отмена", size_hint_x=1, size_hint_y=None, height="44dp",
            on_release=lambda *_: modal.dismiss()))
        modal.add_widget(outer)
        self.word_table_picker = modal
        modal.open()

    def _insert_word_table(self, rows, cols, modal=None):
        if modal:
            modal.dismiss()
        editor = ModalView(size_hint=(0.96, 0.88), auto_dismiss=False)
        outer = MDBoxLayout(orientation="vertical", padding="10dp", spacing="8dp")
        outer.add_widget(MDLabel(text="Заполните ячейки таблицы " + str(rows) + "×" + str(cols),
                                 size_hint_y=None, height="42dp", halign="center", bold=True))
        scroll = ScrollView(do_scroll_x=True, do_scroll_y=True)
        grid = GridLayout(cols=cols, size_hint=(None, None), spacing="3dp",
                          row_default_height="52dp", row_force_default=True)
        grid.bind(minimum_width=grid.setter("width"), minimum_height=grid.setter("height"))
        fields = []
        for _r in range(rows):
            for _c in range(cols):
                field = TextInput(multiline=False, hint_text="Текст",
                                  size_hint=(None, None), size=("128dp", "52dp"),
                                  font_size="14sp")
                grid.add_widget(field)
                fields.append(field)
        scroll.add_widget(grid)
        outer.add_widget(scroll)
        actions = MDBoxLayout(size_hint_y=None, height="48dp", spacing="6dp")
        actions.add_widget(MDFillRoundFlatButton(text="Вставить в Word", on_release=lambda *_:
            self._commit_word_table(rows, cols, fields, editor)))
        actions.add_widget(MDFillRoundFlatButton(text="Отмена", on_release=lambda *_: editor.dismiss()))
        outer.add_widget(actions)
        editor.add_widget(outer)
        self.word_table_editor = editor
        editor.open()

    def _commit_word_table(self, rows, cols, fields, editor):
        try:
            values = [[fields[r * cols + c].text for c in range(cols)] for r in range(rows)]
            self.current_file_bytes = self._get_processor().add_table_to_docx(
                self.current_file_bytes, rows, cols, values)
            self.root.ids.file_content_view.text = self._get_processor().read_word_bytes(
                self.current_file_bytes)
            editor.dismiss()
            self.root.ids.status_label.text = "Таблица " + str(rows) + "×" + str(cols) + " добавлена. Нажмите «Сохранить»."
        except Exception as exc:
            self.root.ids.status_label.text = "Не удалось вставить таблицу: " + str(exc)

    def add_slide_to_presentation(self):
        if self.current_file_format != "pptx":
            self.root.ids.status_label.text = "Добавление слайдов доступно в PowerPoint."
            return
        try:
            self.current_file_bytes = self._get_processor().modify_pptx_bytes(
                self.current_file_bytes, self.root.ids.file_content_view.text)
            self.current_file_bytes = self._get_processor().add_slide_to_pptx(self.current_file_bytes)
            self.root.ids.file_content_view.text = self._get_processor().read_pptx_bytes(self.current_file_bytes)
            self.root.ids.status_label.text = "Добавлен новый слайд. Нажмите «Сохранить»."
            Clock.schedule_once(lambda _dt: self.show_presentation_editor(), 0.15)
        except Exception as exc:
            self.root.ids.status_label.text = "Не удалось добавить слайд: " + str(exc)

    def add_picture_to_document(self):
        if platform != "android" or self.current_file_format not in ("docx", "pptx"):
            self.root.ids.status_label.text = "Добавление изображений доступно в Word и PowerPoint."
            return
        try:
            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("image/*")
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            activity.bind(on_activity_result=self.on_image_selected)
            autoclass("org.kivy.android.PythonActivity").mActivity.startActivityForResult(intent, 1014)
        except Exception as exc:
            self.root.ids.status_label.text = "Не удалось выбрать изображение: " + str(exc)

    def on_image_selected(self, request_code, result_code, intent):
        if request_code != 1014:
            return
        activity.unbind(on_activity_result=self.on_image_selected)
        Activity = autoclass("android.app.Activity")
        if result_code != Activity.RESULT_OK or intent is None or intent.getData() is None:
            return
        try:
            resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
            image_stream = resolver.openInputStream(intent.getData())
            if image_stream is None:
                raise IOError("Android не предоставил доступ к выбранному изображению.")
            data = self._read_android_stream(image_stream)
            if not data:
                raise ValueError("Выбранное изображение пустое или недоступно.")
            processor = self._get_processor()
            if self.current_file_format == "pptx":
                self.current_file_bytes = processor.add_image_to_pptx(self.current_file_bytes, data)
            else:
                self.current_file_bytes = processor.add_image_to_docx(self.current_file_bytes, data)
            self.root.ids.status_label.text = "Изображение добавлено. Нажмите «Сохранить»."
            if self.current_file_format == "pptx" and getattr(self, "presentation_editor", None):
                self.presentation_editor.dismiss()
                Clock.schedule_once(lambda _dt: self.show_presentation_editor(), 0.15)
        except Exception as exc:
            self.root.ids.status_label.text = "Не удалось вставить изображение: " + str(exc)

    def _editor_selection_wrap(self, opening, closing):
        editor = getattr(self, "word_editor_input", None)
        if editor is None:
            return
        start = getattr(editor, "selection_from", None)
        end = getattr(editor, "selection_to", None)
        if start is None or end is None or start == end:
            self.root.ids.status_label.text = "Сначала выделите текст, затем примените формат."
            return
        left, right = sorted((start, end))
        value = editor.text
        editor.text = value[:left] + opening + value[left:right] + closing + value[right:]
        editor.cursor = editor.get_cursor_from_index(left + len(opening) + (right-left) + len(closing))
        editor.cancel_selection()

    def apply_word_bold(self):
        self._editor_selection_wrap("[b]", "[/b]")

    def apply_word_color(self, color):
        self._editor_selection_wrap("[color=" + color + "]", "[/color]")

    def apply_word_highlight(self):
        self._editor_selection_wrap("[highlight=#FFF176]", "[/highlight]")

    def show_fullscreen_text_editor(self, text):
        modal = ModalView(size_hint=(1, 1), auto_dismiss=False,
                          background_color=(0.02, 0.04, 0.08, 0.88))
        outer = MDBoxLayout(orientation="vertical", padding="10dp", spacing="8dp")
        header = MDBoxLayout(size_hint_y=None, height="48dp", spacing="6dp")
        header.add_widget(MDLabel(text=self.current_file_name or "Редактор",
                                  bold=True, valign="middle"))
        header.add_widget(MDFillRoundFlatButton(text="Сохранить",
            on_release=lambda *_: (setattr(self.root.ids.file_content_view, "text", editor.text),
                                   modal.dismiss(), self.save_changes_to_storage())))
        header.add_widget(MDFillRoundFlatButton(text="Закрыть",
            on_release=lambda *_: modal.dismiss()))
        editor = TextInput(text=text, multiline=True, font_size="18sp",
                           size_hint=(1, 1), background_color=(0.98,0.98,0.98,1),
                           foreground_color=(0.08,0.10,0.13,1), padding="12dp")
        outer.add_widget(header)
        outer.add_widget(editor)
        modal.add_widget(outer)
        self.fullscreen_editor = modal
        self.fullscreen_text_input = editor
        modal.open()

    def show_word_editor(self):
        processor = self._get_processor()
        text = processor.read_word_bytes(self.current_file_bytes)
        modal = ModalView(size_hint=(1, 1), auto_dismiss=False,
                          background_color=(0.02, 0.04, 0.08, 0.92))
        outer = MDBoxLayout(orientation="vertical", padding="8dp", spacing="6dp")
        header = MDBoxLayout(size_hint_y=None, height="46dp", spacing="5dp")
        header.add_widget(MDLabel(text=self.current_file_name or "Word",
                                  bold=True, valign="middle"))
        header.add_widget(MDFillRoundFlatButton(text="Изображение",
            on_release=lambda *_: self.add_picture_to_document()))
        header.add_widget(MDFillRoundFlatButton(text="Таблица",
            on_release=lambda *_: self.add_table_to_word()))
        header.add_widget(MDFillRoundFlatButton(text="Сохранить",
            on_release=lambda *_: self._save_word_editor(modal)))
        header.add_widget(MDFillRoundFlatButton(text="Закрыть",
            on_release=lambda *_: modal.dismiss()))
        toolbar = MDBoxLayout(size_hint_y=None, height="46dp", spacing="4dp")
        toolbar.add_widget(MDFillRoundFlatButton(text="Ж", on_release=lambda *_: self.apply_word_bold()))
        for caption, color in (("Чёрный","#111111"),("Красный","#D32F2F"),
                               ("Синий","#1565C0"),("Зелёный","#16834A")):
            toolbar.add_widget(MDFillRoundFlatButton(text=caption,
                on_release=lambda _btn, value=color: self.apply_word_color(value)))
        toolbar.add_widget(MDFillRoundFlatButton(text="Маркер",
            on_release=lambda *_: self.apply_word_highlight()))
        self.word_editor_input = TextInput(text=text, multiline=True, font_size="18sp",
            size_hint=(1, 1), background_color=(0.99,0.99,0.99,1),
            foreground_color=(0.08,0.10,0.13,1), padding="12dp")
        outer.add_widget(header)
        outer.add_widget(toolbar)
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        content = MDBoxLayout(orientation="vertical", size_hint_y=None, spacing="10dp")
        content.bind(minimum_height=content.setter("height"))
        self.word_editor_input.size_hint_y = None
        self.word_editor_input.height = max(600, self.root.height * 0.62)
        content.add_widget(self.word_editor_input)
        try:
            for index, image_bytes in enumerate(processor.extract_docx_images(self.current_file_bytes)):
                try:
                    texture = CoreImage(io.BytesIO(image_bytes)).texture
                    preview = KivyImage(texture=texture, size_hint=(1,None),
                                        height=min(self.root.width * 0.72, 360),
                                        allow_stretch=True, keep_ratio=True)
                    content.add_widget(preview)
                except Exception:
                    continue
        except Exception:
            pass
        scroll.add_widget(content)
        outer.add_widget(scroll)
        modal.add_widget(outer)
        self.word_editor_modal = modal
        modal.open()

    def _save_word_editor(self, modal):
        try:
            self.current_file_bytes = self._get_processor().modify_word_bytes(
                self.current_file_bytes, self.word_editor_input.text)
            modal.dismiss()
            self.root.ids.status_label.text = "Форматирование Word сохранено. Нажмите «Сохранить» для записи файла."
            self.save_changes_to_storage()
        except Exception as exc:
            self.root.ids.status_label.text = "Ошибка сохранения Word: " + str(exc)

    def show_presentation_editor(self):
        processor = self._get_processor()
        slides = processor.extract_pptx_slides(self.current_file_bytes)
        modal = ModalView(size_hint=(1, 1), auto_dismiss=False,
                          background_color=(0.02, 0.04, 0.08, 0.92))
        outer = MDBoxLayout(orientation="vertical", padding="8dp", spacing="6dp")
        header = MDBoxLayout(size_hint_y=None, height="48dp", spacing="5dp")
        header.add_widget(MDLabel(text=self.current_file_name or "PowerPoint",
                                  bold=True, valign="middle"))
        header.add_widget(MDFillRoundFlatButton(text="+ Слайд",
            on_release=lambda *_: (modal.dismiss(), self.add_slide_to_presentation())))
        header.add_widget(MDFillRoundFlatButton(text="Изображение",
            on_release=lambda *_: self.add_picture_to_document()))
        header.add_widget(MDFillRoundFlatButton(text="Сохранить",
            on_release=lambda *_: (modal.dismiss(), self.save_changes_to_storage())))
        header.add_widget(MDFillRoundFlatButton(text="Закрыть",
            on_release=lambda *_: modal.dismiss()))
        outer.add_widget(header)
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        listing = MDBoxLayout(orientation="vertical", size_hint_y=None, spacing="12dp")
        listing.bind(minimum_height=listing.setter("height"))
        for slide_number, slide in enumerate(slides, start=1):
            card = MDCard(orientation="vertical", size_hint_y=None, height="420dp",
                          padding="12dp", spacing="8dp", radius=[12,12,12,12],
                          md_bg_color=(1,1,1,1))
            card.add_widget(MDLabel(text="Слайд " + str(slide_number),
                                    bold=True, theme_text_color="Custom",
                                    text_color=(0.1,0.2,0.3,1),
                                    size_hint_y=None, height="30dp"))
            slide_text = "\n".join(slide.get("texts", [])) or "(Пустой слайд)"
            label = MDLabel(text=slide_text, theme_text_color="Custom",
                            text_color=(0.08,0.1,0.14,1), halign="left",
                            valign="top", size_hint_y=None, height="100dp")
            label.bind(width=lambda w,v: setattr(w,"text_size",(v,None)))
            card.add_widget(label)
            for image_bytes in slide.get("images", [])[:3]:
                try:
                    texture = CoreImage(io.BytesIO(image_bytes)).texture
                    card.add_widget(KivyImage(texture=texture, size_hint=(1,None),
                        height="100dp", allow_stretch=True, keep_ratio=True))
                except Exception:
                    continue
            listing.add_widget(card)
        scroll.add_widget(listing)
        outer.add_widget(scroll)
        modal.add_widget(outer)
        self.presentation_editor = modal
        modal.open()

    def _build_updated_document(self):
        processor = self._get_processor()
        new_text = (self.word_editor_input.text if self.current_file_format == "docx" and getattr(self, "word_editor_input", None)
                    else self.fullscreen_text_input.text if getattr(self, "fullscreen_text_input", None)
                    and self.current_file_format in ("txt", "pdf") else self.root.ids.file_content_view.text)
        writers = {
            "txt": lambda: processor.modify_txt_bytes(new_text),
            "docx": lambda: processor.modify_word_bytes(self.current_file_bytes, new_text),
            "xlsx": lambda: processor.modify_excel_bytes(self.current_file_bytes, new_text),
            "pdf": lambda: processor.modify_pdf_bytes(self.current_file_bytes, new_text),
            "pptx": lambda: processor.modify_pptx_bytes(self.current_file_bytes, new_text),
        }
        return writers[self.current_file_format]()

    def save_changes_to_storage(self):
        if getattr(self, "current_file_format", "") == "xlsx" and getattr(self, "spreadsheet_cells", None):
            try:
                values = [[cell.text for cell in row] for row in self.spreadsheet_cells]
                self.current_file_bytes = self._get_processor().modify_excel_grid(self.current_file_bytes, values)
                local_path = getattr(self, "current_local_path", None)
                if local_path:
                    with open(local_path, "wb") as stream:
                        stream.write(self.current_file_bytes)
                elif not self.current_uri:
                    self.pending_create_bytes = self.current_file_bytes
                    self._start_create_document()
                else:
                    resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
                    stream = resolver.openOutputStream(self.current_uri, "wt")
                    if stream is None:
                        raise IOError("Android не предоставил доступ для записи.")
                    try:
                        stream.write(self.current_file_bytes)
                        stream.flush()
                    finally:
                        stream.close()
                self.root.ids.status_label.text = "Таблица сохранена."
            except Exception as exc:
                self.root.ids.status_label.text = "Ошибка сохранения таблицы: " + str(exc)
            return
        if platform != "android":
            self.root.ids.status_label.text = "Сохранение доступно в Android-приложении."
            return
        try:
            updated = self._build_updated_document()
            local_path = getattr(self, "current_local_path", None)
            if local_path:
                with open(local_path, "wb") as stream:
                    stream.write(updated)
                self.current_file_bytes = updated
                self.root.ids.status_label.text = f"Файл {self.current_file_name} успешно сохранён."
                self.refresh_document_list()
                return
            if not self.current_uri:
                self.pending_create_bytes = updated
                self._start_create_document()
                return
            resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
            stream = resolver.openOutputStream(self.current_uri, "wt")
            if stream is None:
                raise IOError("Android не предоставил поток записи для этого файла.")
            try:
                stream.write(updated)
                stream.flush()
            finally:
                stream.close()
            self.current_file_bytes = updated
            self.root.ids.status_label.text = f"Файл {self.current_file_name} успешно сохранён."
        except Exception as exc:
            self.root.ids.status_label.text = f"Ошибка сохранения: {exc}"

    def load_local_text(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as file:
                return file.read()
        except Exception:
            return "Файл соглашения не найден."

    def show_info_menu(self):
        en = getattr(self, "language", "ru") == "en"
        modal = ModalView(size_hint=(0.90, 0.58), auto_dismiss=True,
                          background_color=(0.02, 0.05, 0.12, 0.62))
        card = MDCard(orientation="vertical", padding="18dp", spacing="10dp",
                      radius=[24, 24, 24, 24], elevation=8,
                      md_bg_color=self.theme_cls.bg_normal)
        card.add_widget(MDLabel(text="Information" if en else "Информация",
                                font_style="H6", bold=True, size_hint_y=None, height="42dp"))
        card.add_widget(MDLabel(text=("Documents are processed locally on this device."
                                     if en else "Документы обрабатываются локально на этом устройстве."),
                                theme_text_color="Secondary"))
        modal.add_widget(card)
        self.info_view = modal
        modal.open()

    def show_legal_doc(self, filename, title_text):
        if getattr(self, "language", "ru") == "en":
            filename = {"privacy_policy.txt": "privacy_policy_en.txt",
                        "terms_of_use.txt": "terms_of_use_en.txt"}.get(filename, filename)
            title_text = {"Политика": "Privacy Policy",
                          "Условия": "Terms of Use",
                          "Политика конфиденциальности": "Privacy Policy",
                          "Условия использования": "Terms of Use"}.get(title_text, title_text)
        if self.dialog:
            self.dialog.dismiss()
        if getattr(self, "legal_view", None):
            self.legal_view.dismiss()

        modal = ModalView(
            size_hint=(0.92, 0.84),
            auto_dismiss=True,
            background_color=(0, 0, 0, 0.55),
        )
        card = MDCard(
            orientation="vertical",
            padding="18dp",
            spacing="12dp",
            radius=[24, 24, 24, 24],
            elevation=8,
            md_bg_color=self.theme_cls.bg_normal,
        )
        heading = MDLabel(
            text=title_text,
            font_style="H6",
            bold=True,
            size_hint_y=None,
            height="38dp",
            theme_text_color="Primary",
        )
        scroll = ScrollView(do_scroll_x=False, bar_width="3dp")
        body = MDLabel(
            text=self.load_local_text(filename),
            size_hint_y=None,
            halign="left",
            valign="top",
            theme_text_color="Primary",
            font_size="14sp",
        )
        body.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
        body.bind(texture_size=lambda widget, size: setattr(widget, "height", size[1] + 12))
        scroll.add_widget(body)
        close_button = MDFillRoundFlatButton(
            text="ПОНЯТНО",
            pos_hint={"center_x": 0.5},
            on_release=lambda *_: modal.dismiss(),
        )
        card.add_widget(heading)
        card.add_widget(scroll)
        card.add_widget(close_button)
        modal.add_widget(card)
        self.legal_view = modal
        modal.open()


if __name__ == "__main__":
    DocumentLocalApp().run()
