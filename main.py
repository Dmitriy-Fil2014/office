import os
from kivy.utils import platform
from kivy.config import Config
from kivymd.app import MDApp
from kivy.lang import Builder
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDFillRoundFlatButton
from document_core import DocumentProcessor

if platform == 'android':
    from jnius import autoclass, cast
    from android import activity


class DocumentLocalApp(MDApp):
    dialog = None
    consent_dialog = None
    current_uri = None
    current_file_name = ""
    current_file_bytes = b""

    def build(self):
        self.config.setdefaults('General', {'accepted_legal': '0'})
        return Builder.load_file('app.kv')

    def on_start(self):
        accepted = self.config.get('General', 'accepted_legal')
        if accepted == '0':
            self.show_mandatory_consent_dialog()

    def show_mandatory_consent_dialog(self):
        policy_btn = MDFlatButton(
            text="ПОЛИТИКА",
            on_release=lambda x: self.view_doc_from_consent("privacy_policy.txt", "Политика конфиденциальности")
        )
        terms_btn = MDFlatButton(
            text="УСЛОВИЯ",
            on_release=lambda x: self.view_doc_from_consent("terms_of_use.txt", "Условия использования")
        )
        accept_btn = MDFillRoundFlatButton(
            text="Я СОГЛАСЕН, НАЧАТЬ РАБОТУ",
            on_release=self.accept_legal_agreements
        )
        self.consent_dialog = MDDialog(
            title="Ознакомление с условиями",
            text="Приложение работает 100% локально в RAM вашего телефона. Нажимая кнопку согласия, вы принимаете правила работы приложения.",
            buttons=[policy_btn, terms_btn, accept_btn],
            auto_dismiss=False
        )
        self.consent_dialog.open()

    def view_doc_from_consent(self, filename, title_text):
        doc_text = self.load_local_text(filename)
        self.dialog = MDDialog(
            title=title_text, text=doc_text,
            buttons=[MDFlatButton(text="ЗАКРЫТЬ ТЕКСТ", on_release=lambda x: self.dialog.dismiss())]
        )
        self.dialog.open()

    def accept_legal_agreements(self, instance):
        self.config.set('General', 'accepted_legal', '1')
        self.config.write()
        if self.consent_dialog:
            self.consent_dialog.dismiss()

    def open_system_storage(self):
        if platform == 'android':
            Intent = autoclass('android.content.Intent')
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            intent.setType("*/*")
            mime_types = ["application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          "application/pdf",
                          "text/plain"]
            intent.putExtra(Intent.EXTRA_MIME_TYPES, mime_types)
            activity.bind(on_activity_result=self.on_file_selected)
            current_activity = autoclass('org.kivy.android.PythonActivity').mActivity
            current_activity.startActivityForResult(intent, 1012)
        else:
            self.root.ids.status_label.text = "Заглушка ПК. Скомпилируйте APK для Android."

    def on_file_selected(self, request_code, result_code, intent):
        if request_code == 1012:
            activity.unbind(on_activity_result=self.on_file_selected)
            Activity = autoclass('android.app.Activity')
            if result_code == Activity.RESULT_OK and intent is not None:
                self.current_uri = intent.getData()
                self.process_android_uri(self.current_uri)

    def process_android_uri(self, uri):
        try:
            current_activity = autoclass('org.kivy.android.PythonActivity').mActivity
            content_resolver = current_activity.getContentResolver()
            input_stream = content_resolver.openInputStream(uri)

            file_bytes = bytearray()
            buffer = autoclass('java.lang.reflect.Array').newInstance(autoclass('java.lang.Byte').TYPE, 4096)
            while True:
                bytes_read = input_stream.read(buffer)
                if bytes_read == -1:
                    break
                file_bytes.extend(buffer[:bytes_read])
            input_stream.close()

            self.current_file_bytes = bytes(file_bytes)
            self.current_file_name = uri.getPath().lower()

            if ".txt" in self.current_file_name:
                text = DocumentProcessor.read_txt_bytes(self.current_file_bytes)
                self.root.ids.status_label.text = "Файл TXT открыт в RAM."
            elif ".docx" in self.current_file_name:
                text = DocumentProcessor.read_word_bytes(self.current_file_bytes)
                self.root.ids.status_label.text = "Файл Word открыт в RAM."
            elif ".xlsx" in self.current_file_name:
                text = DocumentProcessor.read_excel_bytes(self.current_file_bytes)
                self.root.ids.status_label.text = "Файл Excel открыт в RAM."
            elif ".pdf" in self.current_file_name:
                text = DocumentProcessor.read_pdf_bytes(self.current_file_bytes)
                self.root.ids.status_label.text = "Файл PDF открыт в RAM."
            else:
                text = DocumentProcessor.read_txt_bytes(self.current_file_bytes)
                self.root.ids.status_label.text = "Файл открыт как текст."

            self.root.ids.file_content_view.text = text
            self.root.ids.save_btn.disabled = False
        except Exception as e:
            self.root.ids.file_content_view.text = f"Ошибка: {str(e)}"

    def save_changes_to_storage(self):
        if not self.current_uri or platform != 'android':
            return
        try:
            new_text = self.root.ids.file_content_view.text

            if ".txt" in self.current_file_name:
                updated_bytes = DocumentProcessor.modify_txt_bytes(new_text)
            elif ".docx" in self.current_file_name:
                updated_bytes = DocumentProcessor.modify_word_bytes(self.current_file_bytes, new_text)
            elif ".xlsx" in self.current_file_name:
                updated_bytes = DocumentProcessor.modify_excel_bytes(new_text)
            elif ".pdf" in self.current_file_name:
                updated_bytes = DocumentProcessor.modify_pdf_bytes(self.current_file_bytes, new_text)
            else:
                updated_bytes = DocumentProcessor.modify_txt_bytes(new_text)

            current_activity = autoclass('org.kivy.android.PythonActivity').mActivity
            content_resolver = current_activity.getContentResolver()

            # Локальная жесткая перезапись файла на телефоне без серверов
            output_stream = content_resolver.openOutputStream(self.current_uri, "rwt")
            output_stream.write(updated_bytes)
            output_stream.flush()
            output_stream.close()

            self.current_file_bytes = updated_bytes
            self.root.ids.status_label.text = "Изменения сохранены в файл на телефоне!"
        except Exception as e:
            self.root.ids.status_label.text = f"Ошибка записи: {str(e)}"

    def load_local_text(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "Файл соглашения не найден."

    def show_info_menu(self):
        self.dialog = MDDialog(
            title="Инфо", text="Приложение работает без интернета.",
            buttons=[
                MDFlatButton(text="ПОЛИТИКА",
                             on_release=lambda x: self.show_legal_doc("privacy_policy.txt", "Политика")),
                MDFlatButton(text="УСЛОВИЯ", on_release=lambda x: self.show_legal_doc("terms_of_use.txt", "Условия")),
                MDFlatButton(text="ЗАКРЫТЬ", on_release=lambda x: self.dialog.dismiss())
            ],
        )
        self.dialog.open()

    def show_legal_doc(self, filename, title_text):
        if self.dialog: self.dialog.dismiss()
        self.dialog = MDDialog(title=title_text, text=self.load_local_text(filename),
                               buttons=[MDFlatButton(text="ОК", on_release=lambda x: self.dialog.dismiss())])
        self.dialog.open()


if __name__ == '__main__':
    DocumentLocalApp().run()
