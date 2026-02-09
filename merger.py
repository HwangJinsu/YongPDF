
import json
import os

# Unique keys from main_codex1.py (EN values)
main_keys_en = {
    'app_title': 'YongPDF_text',
    'menu_file': '📁 File',
    'menu_edit': '✏️ Edit',
    'menu_view': '🔍 View',
    'menu_tools': '🔧 Tools',
    'menu_help': 'ℹ️ Help',
    'menu_language': '🌐 Language',
    'lang_ko': 'Korean',
    'lang_en': 'English',
    'lang_ja': 'Japanese',
    'lang_zh-CN': 'Simplified Chinese',
    'lang_zh-TW': 'Traditional Chinese',
    'action_open_pdf': '📂 Open PDF',
    'action_save_session': '💼 Save Session',
    'action_load_session': '💼 Load Session',
    'action_save': '💾 Save',
    'action_save_as': '📝 Save As',
    'action_quit': '🚪 Quit',
    'action_undo': '↩️ Undo',
    'action_redo': '↪️ Redo',
    'action_precise_mode': '🩹 Patch Mode',
    'action_patch_eraser': '🧽 Eraser mode',
    'action_zoom_out': '🔍➖ Zoom Out',
    'action_zoom_in': '🔍➕ Zoom In',
    'action_fit_width': '↔️ Fit Width',
    'action_fit_height': '↕️ Fit Height',
    'action_optimize_patches': '⚡ Optimize All Patches',
    'action_show_patch_info': '📊 Show Patch Info',
    'action_force_text_flatten': '🧱 Preserve Text Flatten',
    'action_prev_page': '⬅️ Previous Page',
    'action_next_page': '➡️ Next Page',
    'action_shortcuts': '⌨️ Shortcuts',
    'action_usage_guide': '❓ User Guide',
    'action_about': 'ℹ️ About',
    'action_license': 'Open Source Licenses',
    'license_popup_title': 'Open Source Licenses',
    'license_content_header': 'This app uses the following open source software.<br>Distributed in compliance with each license.<br><br>',
    'action_font_log_label': 'Font log verbosity: {label}',
    'font_log_level_0': 'Off',
    'font_log_level_1': 'Normal',
    'font_log_level_2': 'Verbose',
    'progress_saving_pdf': 'Saving document…',
    'progress_flatten_overlays': 'Merging text layers…',
    'progress_writing_pdf': 'Writing PDF file…',
    'progress_preparing_fonts': 'Preparing font application…',
    'progress_ensuring_fonts': 'Ensuring fonts on page {page}…',
    'progress_applying_overlay': "Applying overlay on page {page}… '{text}'",
    'dialog_save': 'Save',
    'dialog_save_as': 'Save As',
    'save_success_message': 'Saved the PDF successfully.',
    'save_failed_detail': 'Failed to save the PDF: {error}',
    'save_permission_error_detail': 'Cannot save to the current location. Please choose a different folder.\nError: {error}',
    'overlay_deleted': 'Deleted the selected text layer.',
    'title_unsaved_changes': 'Unsaved Changes',
    'msg_unsaved_changes': 'You have unsaved changes. Save before opening another file?',
    'title_error': 'Error',
    'title_warning': 'Warning',
    'title_success': 'Success',
    'title_info': 'Information',
    'msg_no_pdf': 'No PDF document is open.',
    'msg_open_failed': 'Failed to open PDF: {error}',
    'tooltip_open': 'Open PDF (Ctrl+O)',
    'tooltip_save': 'Save (Ctrl+S)',
    'tooltip_undo': 'Undo (Ctrl+Z)',
    'tooltip_redo': 'Redo (Ctrl+Y)',
    'tooltip_zoom_in': 'Zoom In (Ctrl++)',
    'tooltip_zoom_out': 'Zoom Out (Ctrl+-)',
    'tooltip_fit_width': 'Fit width (Ctrl+0)',
    'tooltip_fit_height': 'Fit height (Ctrl+Shift+0)',
    'tooltip_prev_page': 'Previous Page (Page Up)',
    'tooltip_next_page': 'Next Page (Page Down)',
    'tooltip_goto_page': 'Enter page number and press Enter',
    'goto_page_placeholder': 'Page',
    'tooltip_patch_mode': 'Toggle patch mode',
    'tooltip_patch_eraser': 'Eraser mode (patch only)',
    'tooltip_theme': 'Toggle light/dark theme',
    'page_label_template': 'Page: {current}/{total}',
    'page_label_empty': 'Page: 0/0',
    'zoom_label_template': 'Zoom: {percent}%',
    'viewer_placeholder': 'Open a PDF to begin editing.',
    'shortcuts_text': "📋 Key Shortcuts:\n\n🔍 View:\n • Ctrl + '+' : Zoom in\n • Ctrl + '-' : Zoom out\n • Ctrl + 0 : Fit width\n • Ctrl + Shift + 0 : Fit height\n\n📖 Navigation:\n • Page Up : Previous page\n • Page Down : Next page\n\n✏️ Editing:\n • Arrow keys : Move selected text\n\n📁 File:\n • Ctrl + O : Open PDF\n • Ctrl + S : Save\n • Ctrl + Q : Quit",
    'about_text': "📄 YongPDF_text\n\n🛠️ Key Features:\n • Edit text overlays and background patches\n • Patch mode for quick background cleanup\n • Font installation guidance\n • Multilingual interface\n\n💻 Dev & Channel:\n • Python + PySide6 + PyMuPDF\n • Channel: <a href='https://www.youtube.com/playlist?list=PLs36bSFfggCCUX31PYEH_SNgAmVc3dk_B'>YongTools Studio</a>\n\n",
    'text_editor_title': 'Edit Text',
    'text_label': 'Text',
    'font_label': 'Font',
    'size_label': 'Size',
    'stretch_label': 'Stretch',
    'tracking_label': 'Tracking (%)',
    'color_label': 'Color',
    'style_label': 'Style',
    'style_bold': 'Bold',
    'style_italic': 'Italic',
    'style_underline': 'Underline',
    'force_image_label': 'Render as image (embed text as bitmap)',
    'patch_color_label': 'Patch color',
    'patch_color_pick': 'Specify patch color manually',
    'patch_group_title': 'Patch settings',
    'patch_margin_label_horizontal': 'Horizontal margin (%)',
    'patch_margin_label_vertical': 'Vertical margin (%)',
    'patch_margin_hint': 'Adjust the cover horizontally and vertically between -50% and +50% of the text size.',
    'btn_clear_text': 'Clear',
    'font_combo_all_fonts': '--- All Fonts ---',
    'install_font_button': 'Font installation guide',
    'original_font_group': 'Original font information',
    'original_font_label': '🔤 Original font',
    'font_alias_label': '🆔 Font alias',
    'original_size_label': '📐 Original size',
    'original_style_label': '✨ Original style',
    'install_status_label': '💾 Install status',
    'installed_label': "<span style='color: green;'>✅ Installed ({font})</span>",
    'install_path_label': '📁 Path',
    'not_installed_label': "<span style='color: red;'>❌ Not installed</span>",
    'recommended_font_label': '🤖 Suggested alternative',
    'no_alternative_label': "<i style='color: #999;'>No alternative fonts</i>",
    'install_method_label': '📥 How to install',
    'font_install_link_text': '"{font}" installation guide',
    'font_install_dialog_title': '"{font}" Font Installation',
    'font_install_general_title': 'Font installation guide',
    'font_install_intro_html': "<h3>Installing '{font}'</h3>\n<p><b>Required font:</b> {font}</p>\n<h4>Search and download</h4>\n<p>You can find downloads on the following sites:</p>\n<ul>\n<li><b>Noonnu (Korean fonts):</b> <a href=\"https://noonnu.cc/\">noonnu.cc</a></li>\n<li><b>Adobe Fonts</b></li>\n<li><b>Other public font libraries</b></li>\n</ul>\n<h4>Installing the downloaded font</h4>\n",
    'font_install_general_intro_html': "<h3>Font installation guide</h3>\n<p><b>Original font:</b> {original}</p>\n<p><b>Font name:</b> {clean}</p>\n<h4>Search and download</h4>\n<p>You can find downloads on the following sites:</p>\n<ul>\n<li><b>Noonnu (Korean fonts):</b> <a href=\"https://noonnu.cc/\">noonnu.cc</a></li>\n<li><b>Adobe Fonts</b></li>\n<li><b>Other public font libraries</b></li>\n</ul>\n<h4>Installing the downloaded font</h4>\n",
    'font_install_windows_html': "<p><b>Windows:</b></p>\n<ol>\n<li>Right-click the .ttf or .otf file and choose \"Install\"</li>\n<li>Or copy it into C:\\\\Windows\\\\Fonts</li>\n<li>Restart this application after installation</li>\n</ol>\n",
    'font_install_mac_html': "<p><b>macOS:</b></p>\n<ol>\n<li>Double-click the downloaded .ttf or .otf file</li>\n<li>Click \"Install Font\" in Font Book</li>\n<li>Or copy it to ~/Library/Fonts</li>\n<li>Restart this application after installation</li>\n</ol>\n",
    'font_install_linux_html': "<p><b>Linux:</b></p>\n<ol>\n<li>Copy the font file into ~/.fonts or ~/.local/share/fonts</li>\n<li>Run 'fc-cache -fv' in the terminal</li>\n<li>Restart this application after installation</li>\n</ol>\n",
    'font_install_warning_html': "<h4>Important notes</h4>\n<ul>\n<li>Restart this application so the new font is detected.</li>\n<li>Verify the license before using commercial fonts.</li>\n<li>Search using the exact font name to get accurate results.</li>\n</ul>\n",
    'font_install_sites_html': "<h4>Recommended sources</h4>\n<ul>\n<li><b>Noonnu (Korean fonts):</b> <a href=\"https://noonnu.cc/\">noonnu.cc</a></li>\n<li><b>Adobe Fonts:</b> <a href=\"https://fonts.adobe.com\">fonts.adobe.com</a></li>\n<li><b>Other public archives</b></li>\n</ul>\n",
    'font_install_google_button': "Search \"{font} {suffix}\" on Google",
    'font_install_google_query_suffix': 'Noonnu',
    'font_install_noonnu_button': 'Open noonnu home',
    'button_close': 'Close'
}

# Mapping for common keys between pdf_editor_v2 and main_codex1
common_map = {
    'action_zoom_in': 'zoom_in',
    'action_zoom_out': 'zoom_out',
    'action_light_mode': 'theme_light_mode',
    'action_dark_mode': 'theme_dark_mode',
    'action_undo': 'undo',
    'action_redo': 'redo',
    'action_open_pdf': 'open',
    'action_save': 'save',
    'action_save_as': 'save_as',
    'action_quit': 'exit',
    'action_prev_page': 'prev',
    'action_next_page': 'next',
    'action_fit_width': 'fit_width',
    'action_fit_height': 'fit_height',
    'support_menu': 'support_menu',
    'donate_kakao': 'donate_kakao',
    'donate_paypal': 'donate_paypal',
    'donate_paypal_message': 'donate_paypal_message',
    'donate_image_missing': 'donate_image_missing',
    'btn_yes': 'btn_yes',
    'btn_no': 'btn_no',
    'btn_cancel': 'btn_cancel'
}

def merge_lang(lang_code):
    path = f'i18n/{lang_code}.json'
    if not os.path.exists(path): return
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Add main_codex1 keys
    for k, v_en in main_keys_en.items():
        if k in common_map:
            # Reuse existing translation
            data[k] = data.get(common_map[k], v_en)
        else:
            # If it's a new key, for now we use English or try to translate
            # For the 8 new languages, I should ideally provide translated values
            if k not in data:
                data[k] = v_en # Placeholder, I'll replace with real translations for the 8 langs
                
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

langs = ['id', 'ms', 'fil', 'kk', 'uz', 'bn', 'ur', 'tr']
for l in langs:
    merge_lang(l)
print("Merged 8 languages")
