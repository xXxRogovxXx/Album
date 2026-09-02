# -*- coding: utf-8 -*-
"""
Помощник для фотоальбома.

Как пользоваться:
  1. Кинь новые фото в папку photos/ (или сразу в photos/<альбом>/).
     Имена и язык — любые, программа сама переименует в латиницу.
  2. Запусти «Добавить фото.bat» (или python album_tool.py).
  3. По каждому новому фото укажи альбом, подпись, дату и секрет — нажми
     «Сохранить и далее». Программа сама обновит data.json и index.html.
  4. Чтобы выложить на сайт — запусти «Опубликовать в интернет.bat».
"""
import os, re, json, sys, shutil, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
PHOTOS_DIR = os.path.join(ROOT, "photos")
DATA_JSON = os.path.join(ROOT, "data.json")
INDEX_HTML = os.path.join(ROOT, "index.html")

IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".ogv"}
MEDIA_EXT = IMG_EXT | VIDEO_EXT
MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

TRANSLIT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
    'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
    'с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch',
    'ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
}

def _translit(text):
    out = []
    for ch in text.lower().strip():
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        elif ch in " _-.,'":
            out.append("-")
    s = re.sub(r"-+", "-", "".join(out)).strip("-")
    return s

def slug_file(name):
    """Безопасное латинское имя файла (с расширением)."""
    stem, ext = os.path.splitext(name)
    s = _translit(stem) or "photo"
    return s + ext.lower()

def slug_folder(name):
    """Безопасное латинское имя папки-альбома."""
    return _translit(name) or "album"

def ru_date_from_mtime(path):
    try:
        d = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        return f"{d.day} {MONTHS[d.month]} {d.year}"
    except Exception:
        return ""

def load_data():
    if os.path.exists(DATA_JSON):
        with open(DATA_JSON, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def next_id(data):
    ids = [i.get("id", 0) for i in data if isinstance(i.get("id"), int)]
    return (max(ids) + 1) if ids else 1

def existing_folders():
    if not os.path.isdir(PHOTOS_DIR):
        return []
    return sorted(d for d in os.listdir(PHOTOS_DIR)
                  if os.path.isdir(os.path.join(PHOTOS_DIR, d)))

def scan_new(data):
    """
    Список (slug, filename) новых фото:
      - файлы в photos/<slug>/, которых нет в data.json  -> slug = папка
      - файлы прямо в photos/ (без папки)                 -> slug = ""  (альбом выберешь сам)
    """
    known = {(i.get("folder"), i.get("file")) for i in data}
    pending = []
    if not os.path.isdir(PHOTOS_DIR):
        return pending
    # свободные фото в корне photos/
    for fn in sorted(os.listdir(PHOTOS_DIR)):
        full = os.path.join(PHOTOS_DIR, fn)
        if os.path.isfile(full) and os.path.splitext(fn)[1].lower() in MEDIA_EXT:
            pending.append(("", fn))
    # фото внутри альбомов
    for slug in existing_folders():
        for fn in sorted(os.listdir(os.path.join(PHOTOS_DIR, slug))):
            if os.path.splitext(fn)[1].lower() not in MEDIA_EXT:
                continue
            if (slug, fn) not in known:
                pending.append((slug, fn))
    return pending

def source_path(slug, fn):
    return os.path.join(PHOTOS_DIR, fn) if slug == "" else os.path.join(PHOTOS_DIR, slug, fn)

# ---------- Обновление index.html ----------
def read_album_labels(html):
    m = re.search(r"const ALBUM_LABELS\s*=\s*\{(.*?)\};", html, re.S)
    labels = {}
    if m:
        for k, v in re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', m.group(1)):
            labels[k] = v
    return labels

def write_index(data, labels):
    if not os.path.exists(INDEX_HTML):
        return
    with open(INDEX_HTML, encoding="utf-8") as f:
        html = f.read()

    lines = []
    for k, item in enumerate(data):
        comma = "," if k < len(data) - 1 else ""
        lines.append("  " + json.dumps(item, ensure_ascii=False) + comma)
    embedded = "const EMBEDDED_DATA = [\n" + "\n".join(lines) + "\n];"
    html = re.sub(r"const EMBEDDED_DATA\s*=\s*\[.*?\];", lambda m: embedded, html, count=1, flags=re.S)

    keys = list(labels.keys())
    lab_lines = []
    for k, slug in enumerate(keys):
        comma = "," if k < len(keys) - 1 else ""
        lab_lines.append(f'  {json.dumps(slug, ensure_ascii=False)}: {json.dumps(labels[slug], ensure_ascii=False)}{comma}')
    lab_block = "const ALBUM_LABELS = {\n" + "\n".join(lab_lines) + "\n};"
    html = re.sub(r"const ALBUM_LABELS\s*=\s*\{.*?\};", lambda m: lab_block, html, count=1, flags=re.S)

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)

def import_photo(data, src, slug, title, date, secret):
    """Перенести фото в photos/<slug>/ с латинским именем и добавить запись."""
    folder = os.path.join(PHOTOS_DIR, slug)
    os.makedirs(folder, exist_ok=True)
    target = slug_file(os.path.basename(src))
    base, ext = os.path.splitext(target)
    n = 2
    dst = os.path.join(folder, target)
    while os.path.exists(dst) and os.path.abspath(dst) != os.path.abspath(src):
        target = f"{base}-{n}{ext}"; n += 1
        dst = os.path.join(folder, target)
    if os.path.abspath(dst) != os.path.abspath(src):
        shutil.move(src, dst)
    data.append({
        "id": next_id(data),
        "folder": slug,
        "file": target,
        "title": title.strip() or "Без названия",
        "date": date.strip(),
        "secret": secret.strip() or title.strip(),
    })
    return target

# ======================= GUI =======================
def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox

    data = load_data()
    labels = {}
    if os.path.exists(INDEX_HTML):
        with open(INDEX_HTML, encoding="utf-8") as f:
            labels = read_album_labels(f.read())
    pending = scan_new(data)

    root = tk.Tk()
    root.title("Фотоальбом — добавление фото")
    root.geometry("580x560")
    root.configure(bg="#fff5ef")

    style = ttk.Style()
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("TLabel", background="#fff5ef", foreground="#6d4c41", font=("Segoe UI", 10))
    style.configure("H.TLabel", font=("Georgia", 15, "bold"), background="#fff5ef", foreground="#6d4c41")
    style.configure("Hint.TLabel", foreground="#a06a55", font=("Segoe UI", 9))

    state = {"i": 0, "added": 0}
    wrap = tk.Frame(root, bg="#fff5ef")
    wrap.pack(fill="both", expand=True, padx=22, pady=18)

    head = ttk.Label(wrap, style="H.TLabel"); head.pack(anchor="w")
    progress = ttk.Label(wrap); progress.pack(anchor="w", pady=(0, 12))

    grid = tk.Frame(wrap, bg="#fff5ef"); grid.pack(fill="x")

    ttk.Label(grid, text="Альбом (латиницей)").grid(row=0, column=0, sticky="w", pady=6)
    album_var = tk.StringVar()
    album_box = ttk.Combobox(grid, textvariable=album_var, values=existing_folders(), width=40)
    album_box.grid(row=0, column=1, sticky="we", pady=6)

    ttk.Label(grid, text="Название вкладки").grid(row=1, column=0, sticky="w", pady=6)
    label_var = tk.StringVar()
    ttk.Entry(grid, textvariable=label_var, width=42).grid(row=1, column=1, sticky="we", pady=6)

    ttk.Label(grid, text="Файл").grid(row=2, column=0, sticky="w", pady=6)
    file_lbl = ttk.Label(grid, text="", style="Hint.TLabel")
    file_lbl.grid(row=2, column=1, sticky="w", pady=6)

    ttk.Label(grid, text="Подпись").grid(row=3, column=0, sticky="w", pady=6)
    title_var = tk.StringVar()
    title_entry = ttk.Entry(grid, textvariable=title_var, width=42)
    title_entry.grid(row=3, column=1, sticky="we", pady=6)

    ttk.Label(grid, text="Дата").grid(row=4, column=0, sticky="w", pady=6)
    date_var = tk.StringVar()
    ttk.Entry(grid, textvariable=date_var, width=42).grid(row=4, column=1, sticky="we", pady=6)

    ttk.Label(grid, text="Секрет (3 клика)").grid(row=5, column=0, sticky="nw", pady=6)
    secret_txt = tk.Text(grid, width=42, height=3, font=("Segoe UI", 10), wrap="word")
    secret_txt.grid(row=5, column=1, sticky="we", pady=6)
    grid.columnconfigure(1, weight=1)

    def current(): return pending[state["i"]]

    def show_photo():
        slug, fn = current()
        try: os.startfile(source_path(slug, fn))
        except Exception as e: messagebox.showinfo("Фото", f"Не удалось открыть: {e}")

    def load_current():
        if state["i"] >= len(pending): finish(); return
        slug, fn = current()
        head.config(text="Новое фото")
        progress.config(text=f"{state['i']+1} из {len(pending)}  ·  добавлено: {state['added']}")
        album_var.set(slug)  # для свободных фото пусто — выбери альбом
        label_var.set(labels.get(slug, ""))
        file_lbl.config(text=fn)
        title_var.set("")
        date_var.set(ru_date_from_mtime(source_path(slug, fn)))
        secret_txt.delete("1.0", "end")
        (album_box if slug == "" else title_entry).focus_set()

    def persist():
        save_data(data); write_index(data, labels)

    def save_next():
        raw = album_var.get().strip()
        if not raw:
            messagebox.showwarning("Альбом", "Укажи альбом (например: progulki)"); return
        slug = slug_folder(raw)
        labels[slug] = (label_var.get().strip() or labels.get(slug) or raw)
        try:
            import_photo(data, source_path(*current()), slug,
                         title_var.get(), date_var.get(), secret_txt.get("1.0", "end"))
        except Exception as e:
            messagebox.showerror("Ошибка", str(e)); return
        state["added"] += 1
        persist()
        # обновим список альбомов в выпадашке
        album_box["values"] = existing_folders()
        state["i"] += 1
        load_current()

    def skip():
        state["i"] += 1; load_current()

    def finish():
        for w in wrap.winfo_children(): w.destroy()
        ttk.Label(wrap, text="Готово! 💛", style="H.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(wrap, text=f"Добавлено фото: {state['added']}\n\nОбновлены data.json и index.html.",
                  justify="left").pack(anchor="w")
        ttk.Label(wrap, text="Чтобы выложить на сайт — запусти\n«Опубликовать в интернет.bat».",
                  justify="left").pack(anchor="w", pady=14)
        ttk.Button(wrap, text="Закрыть", command=root.destroy).pack(anchor="w")

    btns = tk.Frame(wrap, bg="#fff5ef"); btns.pack(fill="x", pady=16)
    ttk.Button(btns, text="Открыть фото", command=show_photo).pack(side="left")
    ttk.Button(btns, text="Пропустить", command=skip).pack(side="left", padx=8)
    tk.Button(btns, text="Сохранить и далее ▸", command=save_next,
              bg="#d4a574", fg="white", font=("Segoe UI", 10, "bold"),
              relief="flat", padx=14, pady=7, cursor="hand2").pack(side="right")

    if not pending: finish()
    else: load_current()
    root.mainloop()

# ======================= CLI (проверка) =======================
def run_cli_dry():
    data = load_data()
    pending = scan_new(data)
    print(f"Записей в data.json: {len(data)}")
    # проверка «висячих» записей (файл в json есть, а на диске нет)
    missing = [i for i in data if not os.path.exists(source_path(i.get('folder',''), i.get('file','')))]
    if missing:
        print(f"ВНИМАНИЕ, нет файла на диске у {len(missing)} записей:")
        for i in missing: print("   ", i.get('folder'), '/', i.get('file'))
    print(f"Новых фото найдено: {len(pending)}")
    for slug, fn in pending:
        where = slug or "(корень photos/)"
        print(f"   [{where}] {fn}  ->  {slug_file(fn)}")

if __name__ == "__main__":
    if "--dry" in sys.argv:
        run_cli_dry()
    else:
        run_gui()
