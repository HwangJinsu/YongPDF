
import json
import re
import os

def extract_translations():
    with open('pdf_editor_v2.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the self.translations block
    start_match = re.search(r'self.translations = {', content)
    if not start_match:
        print("Could not find translations block")
        return

    # Extract the dictionary content (basic counting of braces)
    start_pos = start_match.end() - 1
    brace_count = 0
    end_pos = -1
    for i in range(start_pos, len(content)):
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end_pos = i + 1
                break
    
    if end_pos == -1:
        print("Could not find end of translations block")
        return

    dict_str = content[start_pos:end_pos]
    
    # We can't easily eval it because of potential dependencies or formatting
    # Let's try to extract each language block manually
    langs = ['ko', 'en', 'ja', 'zh-CN', 'zh-TW']
    translations = {}
    
    for lang in langs:
        # Match 'lang': { ... }
        pattern = rf"'{lang}':\s*\{{(.*?)\n\s*\d*?\s*\}}," # very rough
        # Better: find lang start, then next lang start or end
        lang_start = dict_str.find(f"'{lang}':")
        if lang_start == -1: continue
        
        # Find opening {
        open_brace = dict_str.find('{', lang_start)
        brace_count = 1
        curr_pos = open_brace + 1
        while brace_count > 0 and curr_pos < len(dict_str):
            if dict_str[curr_pos] == '{': brace_count += 1
            elif dict_str[curr_pos] == '}': brace_count -= 1
            curr_pos += 1
        
        inner_content = dict_str[open_brace:curr_pos]
        
        # Now we have a string that looks like a dict.
        # Since it's python code, let's use a trick to convert it to JSON
        # Replace python specific things if any
        # But wait, it's mostly strings. Let's try to clean it up and use json.loads
        # Or just use a simple regex to find all key-value pairs
        items = {}
        # Pattern for 'key': 'value' or 'key': "value"
        kv_pattern = re.compile(r"'(.*?)':\s*(?:'(.*?)'|"(.*?)")", re.DOTALL)
        # Note: some values might be multiline or have escaped chars
        # For simplicity, let's use a more robust way: execute a small python script that just defines this dict
        
    # Plan B: Just write a python script that imports the class or redefines the dict and exports it
    export_script = f"""
import json
class Dummy:
    def t(self, k): return k
    def __init__(self):
        {dict_str}
        for lang, data in self.translations.items():
            with open(f'i18n/{{lang}}.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
Dummy()"""
    with open('exporter.py', 'w', encoding='utf-8') as f:
        f.write(export_script)
    
    import subprocess
    subprocess.run(['python3', 'exporter.py'])
    os.remove('exporter.py')
    print("Translations exported to i18n/*.json")

if __name__ == "__main__":
    extract_translations()
