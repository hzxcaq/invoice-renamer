import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import load_config, save_config
from extractor import FIELD_DEFINITIONS, extract_invoice_data
from renamer import DEFAULT_TEMPLATE, rename_file


class InvoiceRenamerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("发票金额重命名工具")
        self.root.geometry("960x680")
        self.root.resizable(True, True)

        self.cfg = load_config()
        self.results: list[dict] = []

        self._build_ui()

    def _build_ui(self):
        # 顶部：目录选择
        frame_dir = ttk.LabelFrame(self.root, text="扫描目录", padding=10)
        frame_dir.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.var_dir = tk.StringVar(value=self.cfg.get("last_directory", ""))
        ttk.Entry(frame_dir, textvariable=self.var_dir, state="readonly").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5)
        )
        ttk.Button(frame_dir, text="选择目录", command=self._choose_dir).pack(side=tk.RIGHT)

        # 中部：配置
        frame_cfg = ttk.LabelFrame(self.root, text="配置", padding=10)
        frame_cfg.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame_cfg, text="命名规则:").grid(row=0, column=0, sticky=tk.W)
        self.var_template = tk.StringVar(value=self.cfg.get("template", DEFAULT_TEMPLATE))
        entry_tpl = ttk.Entry(frame_cfg, textvariable=self.var_template, width=60)
        entry_tpl.grid(row=0, column=1, sticky=tk.EW, padx=(5, 0))

        # 可用字段提示
        fields_hint = "  ".join(f"{{{k}}}" for k in FIELD_DEFINITIONS)
        ttk.Label(frame_cfg, text=f"可用字段: {fields_hint}", wraplength=800).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(3, 0)
        )
        desc_text = "  |  ".join(f"{k}: {v}" for k, v in FIELD_DEFINITIONS.items())
        ttk.Label(frame_cfg, text=desc_text, wraplength=800, foreground="gray").grid(
            row=2, column=0, columnspan=2, sticky=tk.W, pady=(2, 0)
        )

        self.var_dry_run = tk.BooleanVar(value=self.cfg.get("dry_run", False))
        ttk.Checkbutton(frame_cfg, text="试运行模式（仅预览，不实际重命名）", variable=self.var_dry_run).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, pady=(5, 0)
        )
        frame_cfg.columnconfigure(1, weight=1)

        # 操作按钮
        frame_btn = ttk.Frame(self.root, padding=5)
        frame_btn.pack(fill=tk.X, padx=10)

        self.btn_start = ttk.Button(frame_btn, text="开始处理", command=self._start)
        self.btn_start.pack(side=tk.LEFT)

        ttk.Button(frame_btn, text="导出日志", command=self._export_log).pack(side=tk.RIGHT)

        # 进度条
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=10, pady=5)

        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.var_status).pack(anchor=tk.W, padx=12)

        # 结果表格
        frame_result = ttk.LabelFrame(self.root, text="处理结果", padding=5)
        frame_result.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        columns = ("原文件名", "新文件名", "状态", "说明")
        self.tree = ttk.Treeview(frame_result, columns=columns, show="headings", height=15)
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("原文件名", width=250)
        self.tree.column("新文件名", width=300)
        self.tree.column("状态", width=60, anchor=tk.CENTER)
        self.tree.column("说明", width=280)

        scrollbar = ttk.Scrollbar(frame_result, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _choose_dir(self):
        initial = self.var_dir.get() or ""
        path = filedialog.askdirectory(initialdir=initial, title="选择发票目录")
        if path:
            self.var_dir.set(path)
            self.cfg["last_directory"] = path
            save_config(self.cfg)

    def _collect_pdfs(self, root_dir: str) -> list[str]:
        pdf_files = []
        for dirpath, _, filenames in os.walk(root_dir):
            for fn in filenames:
                if fn.lower().endswith(".pdf"):
                    pdf_files.append(os.path.join(dirpath, fn))
        return sorted(pdf_files)

    def _start(self):
        directory = self.var_dir.get()
        if not directory or not os.path.isdir(directory):
            messagebox.showwarning("提示", "请先选择一个有效的目录")
            return

        template = self.var_template.get().strip()
        if not template:
            messagebox.showwarning("提示", "命名规则不能为空")
            return

        dry_run = self.var_dry_run.get()

        self.cfg["template"] = template
        self.cfg["dry_run"] = dry_run
        save_config(self.cfg)

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results.clear()

        pdf_files = self._collect_pdfs(directory)
        if not pdf_files:
            messagebox.showinfo("提示", "该目录下未找到 PDF 文件")
            return

        self.btn_start.configure(state="disabled")
        self.progress["maximum"] = len(pdf_files)
        self.progress["value"] = 0
        self.var_status.set(f"处理中... 0/{len(pdf_files)}")

        threading.Thread(
            target=self._process_files, args=(pdf_files, template, dry_run), daemon=True
        ).start()

    def _process_files(self, pdf_files: list[str], template: str, dry_run: bool):
        try:
            success = fail = skip = 0

            for i, pdf_path in enumerate(pdf_files):
                filename = os.path.basename(pdf_path)
                try:
                    fields = extract_invoice_data(pdf_path)
                except Exception as e:
                    fields = {}
                    fields["_error"] = f"异常: {e}"

                # 没有提取到金额则跳过
                if not fields.get("amount"):
                    err = fields.get("_error", "未找到价税合计金额")
                    row = {"原文件名": filename, "新文件名": filename, "状态": "跳过", "说明": err}
                    skip += 1
                else:
                    try:
                        ok, new_name, rename_err = rename_file(pdf_path, fields, template, dry_run)
                    except Exception as e:
                        ok, new_name, rename_err = False, filename, f"异常: {e}"
                    if ok:
                        status = "预览" if dry_run else "成功"
                        amount_display = fields["amount"]
                        row = {"原文件名": filename, "新文件名": new_name, "状态": status, "说明": f"¥{amount_display}"}
                        success += 1
                    else:
                        row = {"原文件名": filename, "新文件名": filename, "状态": "失败", "说明": rename_err}
                        fail += 1

                self.root.after(0, self._on_file_processed, row, i + 1)

            mode_text = "试运行" if dry_run else "完成"
            summary = f"{mode_text} | 成功: {success}  失败: {fail}  跳过: {skip}  共: {len(pdf_files)}"
            self.root.after(0, self._on_all_done, summary)
        except Exception as e:
            self.root.after(0, self._on_all_done, f"处理异常中断: {e}")

    def _on_file_processed(self, row: dict, progress: int):
        self.results.append(row)
        self.tree.insert("", tk.END, values=(row["原文件名"], row["新文件名"], row["状态"], row["说明"]))
        self.progress["value"] = progress
        self.var_status.set(f"处理中... {progress}/{self.progress['maximum']}")

    def _on_all_done(self, summary: str):
        self.var_status.set(summary)
        self.btn_start.configure(state="normal")

    def _export_log(self):
        if not self.results:
            messagebox.showinfo("提示", "没有可导出的结果")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            title="导出处理日志",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write("原文件名,新文件名,状态,说明\n")
                for r in self.results:
                    f.write(f'"{r["原文件名"]}","{r["新文件名"]}","{r["状态"]}","{r["说明"]}"\n')
            messagebox.showinfo("成功", f"日志已导出到:\n{path}")
        except OSError as e:
            messagebox.showerror("错误", f"导出失败: {e}")


def main():
    root = tk.Tk()
    InvoiceRenamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
