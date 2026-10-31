from kivy.utils import platform
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.uix.label import Label
import traceback
import locale
import sys
import os
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

    def build(self):
        self.config.setdefaults("General", {"accepted_legal": "0", "theme_mode": "system", "language": "system"})
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
        Clock.schedule_once(self._finish_startup, 0.65)
        Clock.schedule_once(self._hide_splash, 0.75)

    def _hide_splash(self, _dt):
        try:
            layer = self.root.ids.splash_layer
            animation = Animation(opacity=0, duration=0.28)
            animation.bind(on_complete=lambda *_: self.root.remove_widget(layer))
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
        self.language = self._system_language() if lang == "system" else lang
        self._refresh_language()

    def _refresh_language(self):
        en = getattr(self, "language", "ru") == "en"
        try:
            self.root.ids.status_label.text = "Choose a file. Changes overwrite the document." if en else "Выберите файл. Изменения перезапишут документ."
            self.root.ids.open_btn.text = "OPEN FILE" if en else "ОТКРЫТЬ ФАЙЛ"
            self.root.ids.save_btn.text = "SAVE" if en else "СОХРАНИТЬ"
            self.root.ids.file_content_view.hint_text = "Document text will appear here" if en else "Содержимое документа отобразится здесь"
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
        self.dialog = MDDialog(
            title="Settings" if en else "Настройки",
            text="Choose theme and language" if en else "Выберите тему и язык приложения.",
            buttons=[
                MDFlatButton(text="SYSTEM THEME" if en else "СИСТЕМНАЯ ТЕМА", on_release=lambda x: self.set_theme_mode("system")),
                MDFlatButton(text="DARK" if en else "ТЁМНАЯ", on_release=lambda x: self.set_theme_mode("dark")),
                MDFlatButton(text="LIGHT" if en else "СВЕТЛАЯ", on_release=lambda x: self.set_theme_mode("light")),
                MDFlatButton(text="РУССКИЙ", on_release=lambda x: self.set_language("ru")),
                MDFlatButton(text="ENGLISH", on_release=lambda x: self.set_language("en")),
                MDFlatButton(text="SYSTEM LANG" if en else "ЯЗЫК СИСТЕМЫ", on_release=lambda x: self.set_language("system")),
            ],
        )
        self.dialog.open()

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
        policy_btn = MDFlatButton(
            text="ПОЛИТИКА",
            on_release=lambda x: self.view_doc_from_consent(
                "privacy_policy.txt", "Политика конфиденциальности"
            ),
        )
        terms_btn = MDFlatButton(
            text="УСЛОВИЯ",
            on_release=lambda x: self.view_doc_from_consent(
                "terms_of_use.txt", "Условия использования"
            ),
        )
        accept_btn = MDFillRoundFlatButton(
            text="Я СОГЛАСЕН, НАЧАТЬ РАБОТУ",
            on_release=self.accept_legal_agreements,
        )
        self.consent_dialog = MDDialog(
            title="Ознакомление с условиями",
            text="Приложение работает локально на вашем устройстве. "
                 "Нажимая кнопку согласия, вы принимаете правила работы приложения.",
            buttons=[policy_btn, terms_btn, accept_btn],
            auto_dismiss=False,
        )
        self.consent_dialog.open()

    def view_doc_from_consent(self, filename, title_text):
        self.dialog = MDDialog(
            title=title_text,
            text=self.load_local_text(filename),
            buttons=[
                MDFlatButton(
                    text="ЗАКРЫТЬ ТЕКСТ",
                    on_release=lambda x: self.dialog.dismiss(),
                )
            ],
        )
        self.dialog.open()

    def accept_legal_agreements(self, instance):
        self.config.set("General", "accepted_legal", "1")
        self.config.write()
        if self.consent_dialog:
            self.consent_dialog.dismiss()

    def show_new_document_menu(self):
        self.dialog = MDDialog(
            title="Создать документ",
            text="Выберите формат нового файла",
            buttons=[
                MDFlatButton(text="WORD", on_release=lambda x: self.create_new_document("docx")),
                MDFlatButton(text="EXCEL", on_release=lambda x: self.create_new_document("xlsx")),
                MDFlatButton(text="POWERPOINT", on_release=lambda x: self.create_new_document("pptx")),
                MDFlatButton(text="TXT", on_release=lambda x: self.create_new_document("txt")),
            ],
        )
        self.dialog.open()

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
            self.current_uri = None
            self.root.ids.file_content_view.text = "[Слайд 1]" if file_format == "pptx" else ""
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
        if request_code != 1012:
            return
        activity.unbind(on_activity_result=self.on_file_selected)
        Activity = autoclass("android.app.Activity")
        if result_code == Activity.RESULT_OK and intent is not None:
            self.current_uri = intent.getData()
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
            current_activity = autoclass(
                "org.kivy.android.PythonActivity"
            ).mActivity
            resolver = current_activity.getContentResolver()
            self.current_file_name, mime_type = self._get_file_metadata(
                uri, resolver
            )
            DocumentProcessor = self._get_processor()
            self.current_file_format = DocumentProcessor.detect_format(
                self.current_file_name, mime_type
            )

            input_stream = resolver.openInputStream(uri)
            if input_stream is None:
                raise IOError("Android не смог открыть выбранный файл.")
            self.current_file_bytes = self._read_android_stream(input_stream)

            readers = {
                "txt": DocumentProcessor.read_txt_bytes,
                "docx": DocumentProcessor.read_word_bytes,
                "xlsx": DocumentProcessor.read_excel_bytes,
                "pdf": DocumentProcessor.read_pdf_bytes,
                "pptx": DocumentProcessor.read_pptx_bytes,
            }
            text = readers[self.current_file_format](self.current_file_bytes)
            self.root.ids.file_content_view.text = text
            self.root.ids.save_btn.disabled = False
            self.root.ids.status_label.text = (
                f"Открыт {self.current_file_name}. "
                "Редактирование выполняется локально."
            )
        except Exception as exc:
            self._write_startup_error("Ошибка чтения документа")
            self.root.ids.file_content_view.text = ""
            self.root.ids.save_btn.disabled = True
            self.root.ids.status_label.text = f"Ошибка открытия: {exc}"

    def save_changes_to_storage(self):
        if not self.current_uri or platform != "android":
            self.root.ids.status_label.text = "Сначала откройте документ."
            return
        try:
            DocumentProcessor = self._get_processor()
            new_text = self.root.ids.file_content_view.text
            writers = {
                "txt": lambda: DocumentProcessor.modify_txt_bytes(new_text),
                "docx": lambda: DocumentProcessor.modify_word_bytes(
                    self.current_file_bytes, new_text
                ),
                "xlsx": lambda: DocumentProcessor.modify_excel_bytes(
                    self.current_file_bytes, new_text
                ),
                "pdf": lambda: DocumentProcessor.modify_pdf_bytes(
                    self.current_file_bytes, new_text
                ),
                "pptx": lambda: DocumentProcessor.modify_pptx_bytes(
                    self.current_file_bytes, new_text
                ),
            }
            updated_bytes = writers[self.current_file_format]()

            current_activity = autoclass(
                "org.kivy.android.PythonActivity"
            ).mActivity
            resolver = current_activity.getContentResolver()
            output_stream = None
            try:
                output_stream = resolver.openOutputStream(self.current_uri, "rwt")
            except Exception:
                output_stream = resolver.openOutputStream(self.current_uri, "wt")
            if output_stream is None:
                raise IOError("Android не предоставил поток записи для этого файла.")
            try:
                output_stream.write(updated_bytes)
                output_stream.flush()
            finally:
                output_stream.close()

            self.current_file_bytes = updated_bytes
            self.root.ids.status_label.text = (
                f"Файл {self.current_file_name} успешно сохранён."
            )
        except Exception as exc:
            self.root.ids.status_label.text = f"Ошибка сохранения: {exc}"

    def load_local_text(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as file:
                return file.read()
        except Exception:
            return "Файл соглашения не найден."

    def show_info_menu(self):
        self.dialog = MDDialog(
            title="Информация",
            text="Документы обрабатываются локально на устройстве.",
            buttons=[
                MDFlatButton(
                    text="ПОЛИТИКА",
                    on_release=lambda x: self.show_legal_doc(
                        "privacy_policy.txt", "Политика"
                    ),
                ),
                MDFlatButton(
                    text="УСЛОВИЯ",
                    on_release=lambda x: self.show_legal_doc(
                        "terms_of_use.txt", "Условия"
                    ),
                ),
                MDFlatButton(
                    text="ЗАКРЫТЬ",
                    on_release=lambda x: self.dialog.dismiss(),
                ),
            ],
        )
        self.dialog.open()

    def show_legal_doc(self, filename, title_text):
        if self.dialog:
            self.dialog.dismiss()
        self.dialog = MDDialog(
            title=title_text,
            text=self.load_local_text(filename),
            buttons=[
                MDFlatButton(
                    text="ОК",
                    on_release=lambda x: self.dialog.dismiss(),
                )
            ],
        )
        self.dialog.open()


if __name__ == "__main__":
    DocumentLocalApp().run()
