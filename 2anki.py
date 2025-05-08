import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import csv # No longer used for output, but kept for os.path etc.
import os
import re
import traceback
import requests # For AnkiConnect API calls
import json     # For AnkiConnect API calls

# --- AnkiConnect Helper Functions ---
ANKICONNECT_URL = "http://127.0.0.1:8765" # Default AnkiConnect URL

def anki_invoke(action, log_callback=print, **params):
    request_json = {'action': action, 'params': params, 'version': 6}
    log_callback(f"AnkiConnect 请求: action={action}, params={json.dumps(params, ensure_ascii=False)}")
    try:
        response = requests.post(ANKICONNECT_URL, json=request_json, timeout=5) # Added timeout
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        response_data = response.json()
        log_callback(f"AnkiConnect 响应: {json.dumps(response_data, ensure_ascii=False)}")
        
        if response_data.get('error') is not None:
            log_callback(f"AnkiConnect API 错误: {response_data['error']}")
            return None # Or raise an exception
        return response_data.get('result') # Return the 'result' part of the response

    except requests.exceptions.Timeout:
        log_callback(f"AnkiConnect API 调用超时。请确保 Anki 正在运行且 AnkiConnect 已加载。")
        messagebox.showerror("AnkiConnect 错误", "连接 AnkiConnect 超时。\n请确保 Anki 正在运行且 AnkiConnect 插件已正确加载。")
        return None
    except requests.exceptions.ConnectionError:
        log_callback(f"AnkiConnect API 连接失败。请确保 Anki 正在运行且 AnkiConnect 已加载并监听 {ANKICONNECT_URL}。")
        messagebox.showerror("AnkiConnect 错误", f"无法连接到 AnkiConnect ({ANKICONNECT_URL})。\n请确保 Anki 正在运行且 AnkiConnect 插件已正确加载。")
        return None
    except requests.exceptions.RequestException as e:
        log_callback(f"AnkiConnect API 调用失败: {e}")
        messagebox.showerror("AnkiConnect 错误", f"AnkiConnect API 调用失败: {e}")
        return None
    except json.JSONDecodeError:
        log_callback(f"无法解析 AnkiConnect 的响应: {response.text}")
        messagebox.showerror("AnkiConnect 错误", f"无法解析 AnkiConnect 的响应。")
        return None

def check_anki_connection(log_callback=print):
    log_callback("正在检查 AnkiConnect 连接...")
    if anki_invoke('deckNames', log_callback=log_callback) is not None:
        log_callback("AnkiConnect 连接成功！")
        return True
    else:
        log_callback("AnkiConnect 连接失败。")
        # messagebox.showerror("AnkiConnect 错误", "无法连接到 Anki。请确保 Anki 正在运行且 AnkiConnect 插件已启用。")
        return False

def get_anki_deck_names(log_callback=print):
    return anki_invoke('deckNames', log_callback=log_callback) or []

def get_anki_model_names(log_callback=print):
    return anki_invoke('modelNames', log_callback=log_callback) or []

def get_anki_model_field_names(model_name, log_callback=print):
    if not model_name:
        return []
    return anki_invoke('modelFieldNames', modelName=model_name, log_callback=log_callback) or []


# --- Markdown Parsing (逐行匹配 - 保留原始格式) ---
def parse_markdown_to_sections_raw_format(md_filepath, log_callback):
    # This function now only parses and returns sections, does not write CSV
    if not md_filepath:
        log_callback("错误：未选择 Markdown 输入文件。")
        return None # Return None on error

    try:
        with open(md_filepath, 'r', encoding='utf-8-sig') as md_file:
            lines = md_file.readlines()
        log_callback(f"成功读取 Markdown 文件: {md_filepath} (共 {len(lines)} 行)")
    except FileNotFoundError:
        log_callback(f"错误：Markdown 文件未找到: {md_filepath}")
        return None
    except Exception as e:
        log_callback(f"错误：读取 Markdown 文件时发生错误: {e}")
        log_callback(traceback.format_exc())
        return None

    h4_plus_title_pattern = re.compile(r"^(#{4,6})\s+(.*)")
    extracted_sections = []
    current_title_text = None
    current_content_lines = []
    in_h4_plus_section = False

    for line_number, raw_line_from_readlines in enumerate(lines, 1):
        line_for_match = raw_line_from_readlines.rstrip('\n')
        title_match = h4_plus_title_pattern.match(line_for_match)

        if title_match:
            title_hashes = title_match.group(1)
            title_text_content = title_match.group(2).strip()
            log_callback(f"L{line_number}: 匹配到 H{len(title_hashes)} 标题: '{title_text_content}'")

            if in_h4_plus_section and current_title_text is not None:
                content_block = "".join(current_content_lines)
                if current_title_text or content_block.strip():
                    extracted_sections.append((current_title_text, content_block))
            
            current_title_text = title_text_content
            current_content_lines = []
            in_h4_plus_section = True

        elif in_h4_plus_section:
            current_content_lines.append(raw_line_from_readlines)

    if in_h4_plus_section and current_title_text is not None:
        content_block = "".join(current_content_lines)
        if current_title_text or content_block.strip():
             extracted_sections.append((current_title_text, content_block))
    
    log_callback(f"Markdown 解析完成，提取到 {len(extracted_sections)} 个 H4+ 部分。")
    return extracted_sections


# --- Main Conversion and Anki Upload Logic ---
def convert_and_upload_to_anki(md_filepath, anki_config, log_callback):
    deck_name = anki_config["deck_name"]
    model_name = anki_config["model_name"]
    front_field = anki_config["front_field"]
    back_field = anki_config["back_field"]
    tags_str = anki_config["tags"]
    tags_list = [tag.strip() for tag in tags_str.split(',') if tag.strip()] if tags_str else []

    if not all([deck_name, model_name, front_field, back_field]):
        log_callback("错误：Anki 配置不完整 (牌组、模型、正反面字段为必填项)。")
        messagebox.showerror("配置错误", "请填写所有 Anki 配置项。")
        return False

    if not check_anki_connection(log_callback):
        return False

    log_callback(f"开始解析 Markdown 文件: {md_filepath}")
    sections = parse_markdown_to_sections_raw_format(md_filepath, log_callback)

    if sections is None: # Error during parsing
        log_callback("Markdown 文件解析失败，取消上传。")
        return False
    
    if not sections:
        log_callback(f"在 '{os.path.basename(md_filepath)}' 中未找到 H4+ 标题部分。无需上传。")
        messagebox.showinfo("无内容", "未在 Markdown 文件中找到符合条件的 H4+ 标题部分。")
        return True # No error, just nothing to upload

    added_notes_count = 0
    failed_notes_count = 0
    log_callback(f"开始将 {len(sections)} 个部分添加到 Anki...")

    # 准备批量添加的笔记数据
    notes_to_add = []
    for heading, content in sections:
        # Anki字段区分大小写，确保用户输入或我们代码中的名称与Anki中一致
        fields_data = {
            front_field: heading,
            back_field: content # 内容直接发送，Anki会处理其中的HTML/Markdown (取决于字段设置)
        }
        note_params = {
            "deckName": deck_name,
            "modelName": model_name,
            "fields": fields_data,
            "options": {
                "allowDuplicate": False, # 可以根据需要调整
                # "duplicateScope": "deck", # 检查重复范围，可选
                # "duplicateScopeOptions": {"deckName": deck_name, "checkChildren": False}
            },
            "tags": tags_list
        }
        notes_to_add.append(note_params)

    # 使用 addNotes 进行批量添加 (更高效)
    if notes_to_add:
        results = anki_invoke('addNotes', log_callback=log_callback, notes=notes_to_add)
        if results is not None: # results is a list of IDs or nulls
            for i, result_id in enumerate(results):
                heading, _ = sections[i]
                if result_id is not None:
                    added_notes_count += 1
                    log_callback(f"成功添加笔记: '{heading}' (ID: {result_id})")
                else:
                    failed_notes_count += 1
                    # The API response for addNotes with errors usually provides nulls.
                    # More detailed error info might require individual addNote calls or checking Anki's debug logs.
                    log_callback(f"添加笔记失败: '{heading}'. (可能重复或字段问题，请检查AnkiConnect的详细错误)") # More specific error might be in the global 'error' of response if all fail
        else:
            # This case means the 'addNotes' action itself failed (e.g., bad request structure)
            # not individual note failures which are indicated by nulls in the results list.
            failed_notes_count = len(notes_to_add) # Assume all failed if action fails
            log_callback(f"AnkiConnect 'addNotes' 批量操作失败。")


    log_callback(f"Anki 添加完成。成功: {added_notes_count} 条，失败: {failed_notes_count} 条。")
    if failed_notes_count > 0:
        messagebox.showwarning("添加部分失败", f"成功添加 {added_notes_count} 条笔记到 Anki。\n有 {failed_notes_count} 条笔记添加失败，请检查日志和 AnkiConnect 控制台获取详细信息。")
    elif added_notes_count > 0:
        messagebox.showinfo("完成", f"成功添加 {added_notes_count} 条笔记到 Anki！")
    # If no notes were added but also no failures (e.g. empty sections list), this is handled earlier.
    return True


# Helper for logging (no change)
def replace_LF_CR_with_visible_chars(s):
    if not isinstance(s, str): s = str(s)
    return s.replace("\n", "\\n").replace("\r", "\\r")

# --- GUI部分 ---
class MdToAnkiApp:
    def __init__(self, master):
        self.master = master
        master.title("Markdown 转 Anki 工具 (AnkiConnect)")
        master.geometry("750x750") # Adjusted size

        self.md_file_path = tk.StringVar()

        # --- File Selection Frame ---
        file_frame = ttk.LabelFrame(master, text="1. 选择 Markdown 文件", padding=(10, 10))
        file_frame.pack(padx=10, pady=5, fill="x")

        ttk.Label(file_frame, text="Markdown 文件:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.md_entry = ttk.Entry(file_frame, textvariable=self.md_file_path, width=70)
        self.md_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.md_browse_button = ttk.Button(file_frame, text="浏览...", command=self.browse_md_file)
        self.md_browse_button.grid(row=0, column=2, sticky="w", padx=5, pady=5)
        file_frame.columnconfigure(1, weight=1)

        # --- Anki Configuration Frame ---
        anki_frame = ttk.LabelFrame(master, text="2. Anki 配置", padding=(10, 10))
        anki_frame.pack(padx=10, pady=5, fill="x")

        self.deck_names = []
        self.model_names = []
        self.front_field_names = []
        self.back_field_names = []

        # Deck Name
        ttk.Label(anki_frame, text="牌组名称 (Deck):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.deck_name_var = tk.StringVar()
        self.deck_combo = ttk.Combobox(anki_frame, textvariable=self.deck_name_var, width=38, state="readonly")
        self.deck_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        self.refresh_decks_button = ttk.Button(anki_frame, text="刷新牌组", command=self.populate_deck_names)
        self.refresh_decks_button.grid(row=0, column=2, padx=5, pady=2)

        # Model Name
        ttk.Label(anki_frame, text="笔记类型 (Note Type):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.model_name_var = tk.StringVar()
        self.model_combo = ttk.Combobox(anki_frame, textvariable=self.model_name_var, width=38, state="readonly")
        self.model_combo.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        self.refresh_models_button = ttk.Button(anki_frame, text="刷新类型", command=self.populate_model_names)
        self.refresh_models_button.grid(row=1, column=2, padx=5, pady=2)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_selected)


        # Front Field
        ttk.Label(anki_frame, text="正面卡片字段 (Front):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.front_field_var = tk.StringVar()
        self.front_field_combo = ttk.Combobox(anki_frame, textvariable=self.front_field_var, width=38, state="readonly")
        self.front_field_combo.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        # Back Field
        ttk.Label(anki_frame, text="背面卡片字段 (Back):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.back_field_var = tk.StringVar()
        self.back_field_combo = ttk.Combobox(anki_frame, textvariable=self.back_field_var, width=38, state="readonly")
        self.back_field_combo.grid(row=3, column=1, sticky="ew", padx=5, pady=2)
        
        # Refresh Fields button (for selected model)
        self.refresh_fields_button = ttk.Button(anki_frame, text="刷新字段", command=lambda: self.on_model_selected(None)) # Reuse on_model_selected
        self.refresh_fields_button.grid(row=2, column=2, rowspan=2, padx=5, pady=2, sticky="ns")


        # Tags
        ttk.Label(anki_frame, text="标签 (Tags, 逗号分隔):").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.tags_var = tk.StringVar()
        self.tags_entry = ttk.Entry(anki_frame, textvariable=self.tags_var, width=40)
        self.tags_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
        
        anki_frame.columnconfigure(1, weight=1)

        # --- Action Button ---
        self.convert_button = ttk.Button(master, text="开始转换并添加到 Anki", command=self.start_conversion_process, style="Accent.TButton", padding=(10,5))
        self.convert_button.pack(pady=15)

        # --- Log Frame ---
        log_frame = ttk.LabelFrame(master, text="日志", padding=(10,5))
        log_frame.pack(padx=10, pady=(0,10), fill="both", expand=True)
        self.log_text_widget = tk.Text(log_frame, height=15, state="disabled", wrap=tk.WORD, bg="#2b2b2b", fg="#dcdcdc", font=("Consolas", 9))
        self.log_text_widget.pack(side=tk.LEFT, fill="both", expand=True, padx=(0,5))
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text_widget.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.log_text_widget.config(yscrollcommand=log_scrollbar.set)

        # --- Initial Population ---
        self.master.after(100, self.initial_anki_load) # Load after GUI is up

    def initial_anki_load(self):
        self.log_message("应用启动，尝试连接 AnkiConnect 并加载初始数据...")
        if check_anki_connection(self.log_message):
            self.populate_deck_names()
            self.populate_model_names()
        else:
            self.log_message("无法连接到 Anki。请确保 Anki 正在运行且 AnkiConnect 已安装。")
            self.log_message("您需要手动点击“刷新”按钮来加载牌组和笔记类型信息。")


    def log_message(self, message):
        self.log_text_widget.config(state="normal")
        self.log_text_widget.insert(tk.END, str(message) + "\n")
        self.log_text_widget.see(tk.END)
        self.log_text_widget.config(state="disabled")
        self.master.update_idletasks()

    def browse_md_file(self):
        filepath = filedialog.askopenfilename(
            title="选择 Markdown 文件",
            filetypes=(("Markdown 文件", "*.md"), ("Text 文件", "*.txt"), ("所有文件", "*.*"))
        )
        if filepath:
            self.md_file_path.set(filepath)
            self.log_message(f"已选择 Markdown 文件: {filepath}")

    def populate_deck_names(self):
        self.log_message("正在获取 Anki 牌组列表...")
        self.deck_names = get_anki_deck_names(self.log_message)
        self.deck_combo['values'] = self.deck_names
        if self.deck_names:
            self.deck_combo.current(0)
        else:
            self.deck_combo.set('')
        self.log_message(f"牌组列表已更新 ({len(self.deck_names)} 个).")

    def populate_model_names(self):
        self.log_message("正在获取 Anki 笔记类型列表...")
        self.model_names = get_anki_model_names(self.log_message)
        self.model_combo['values'] = self.model_names
        if self.model_names:
            self.model_combo.current(0)
            self.on_model_selected(None) # Populate fields for the first model
        else:
            self.model_combo.set('')
            self.front_field_combo.set('')
            self.front_field_combo['values'] = []
            self.back_field_combo.set('')
            self.back_field_combo['values'] = []
        self.log_message(f"笔记类型列表已更新 ({len(self.model_names)} 个).")


    def on_model_selected(self, event): # event can be None if called programmatically
        selected_model = self.model_name_var.get()
        self.log_message(f"笔记类型 '{selected_model}' 已选择，获取其字段...")
        if selected_model:
            field_names = get_anki_model_field_names(selected_model, self.log_message)
            self.front_field_combo['values'] = field_names
            self.back_field_combo['values'] = field_names
            if field_names:
                # Try to intelligently select default fields (e.g. "Front", "Back", or first/second)
                if "Front" in field_names: self.front_field_combo.set("Front")
                elif "正面" in field_names: self.front_field_combo.set("正面")
                else: self.front_field_combo.current(0)
                
                if "Back" in field_names: self.back_field_combo.set("Back")
                elif "背面" in field_names: self.back_field_combo.set("背面")
                elif len(field_names) > 1: self.back_field_combo.current(1)
                else: self.back_field_combo.current(0)

            else:
                self.front_field_combo.set('')
                self.back_field_combo.set('')
            self.log_message(f"模型 '{selected_model}' 的字段已加载: {field_names}")
        else:
            self.front_field_combo['values'] = []
            self.back_field_combo['values'] = []
            self.front_field_combo.set('')
            self.back_field_combo.set('')


    def start_conversion_process(self):
        self.log_text_widget.config(state="normal")
        self.log_text_widget.delete(1.0, tk.END)
        self.log_text_widget.config(state="disabled")
        
        md_path = self.md_file_path.get()
        if not md_path:
            messagebox.showerror("错误", "请先选择一个 Markdown 文件。")
            self.log_message("错误：未选择 Markdown 文件。")
            return

        anki_config = {
            "deck_name": self.deck_name_var.get(),
            "model_name": self.model_name_var.get(),
            "front_field": self.front_field_var.get(),
            "back_field": self.back_field_var.get(),
            "tags": self.tags_var.get()
        }
        
        self.log_message("开始处理并上传到 Anki...")
        self.log_message(f"Anki 配置: {anki_config}")

        # Run conversion and upload in a separate thread or use async if it were a long process
        # For now, direct call for simplicity, GUI might freeze on very large files/many notes
        success = convert_and_upload_to_anki(md_path, anki_config, self.log_message)
        
        if success:
            self.log_message("处理和上传过程完成。")
        else:
            self.log_message("处理或上传过程中发生错误。请检查日志。")

if __name__ == "__main__":
    root = tk.Tk()
    app = MdToAnkiApp(root)
    root.mainloop()