"""知识库管理工具 (v2.1) - 适配新版插件架构

变更说明:
- 使用 importlib.util 直接加载 knowledge_base.py 和 config.py
- 绕过 bpdiscord 包的 __init__.py 链，避免触发 NoneBot 插件注册
- 通过 KnowledgeBaseMemory 封装方法操作知识库
- 配置项由 config.py 统一管理
"""
import sys
import os
import types
import importlib.util
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext


# === 新版架构：自动定位项目根目录 ===
script_dir = Path(__file__).absolute().parent

# 向上查找包含 pyproject.toml 且 name="bpdiscord" 的项目根目录
project_root = None
search_path = script_dir
for _ in range(10):
    toml_path = search_path / "pyproject.toml"
    if toml_path.exists():
        try:
            content = toml_path.read_text(encoding="utf-8")
            if 'name = "bpdiscord"' in content or "name = 'bpdiscord'" in content:
                project_root = search_path
                break
        except Exception:
            pass
    parent = search_path.parent
    if parent == search_path:
        break
    search_path = parent

if not project_root:
    print("\u274c 严重错误：未找到 bpdiscord 项目根目录！")
    print("请确认此脚本放置在 bpdiscord 项目目录内。")
    input("\n按回车键退出...")
    sys.exit(1)

print(f"项目根目录: {project_root}")


def _create_stub_package(name, path_list=None):
    """创建 stub 包，不执行 __init__.py，避免触发 NoneBot 插件注册"""
    stub = types.ModuleType(name)
    stub.__package__ = name
    stub.__path__ = path_list or []
    sys.modules[name] = stub
    return stub


def _load_module_direct(module_name, file_path, package_name=None):
    """通过 importlib.util 直接加载模块，不经过包的 __init__.py 链"""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None:
        raise ImportError(f"Cannot create spec for {module_name} from {file_path}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = package_name or module_name
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# === 关键：用 stub 包构建导入链，绕过 __init__.py ===
# knowledge_base.py 的相对导入 from ...config 需要：
#   bpdiscord.plugins.bpdiscord.config 在 sys.modules 中
# 以及所有中间包在 sys.modules 中

# 1. 创建 stub 包（不执行 __init__.py，不触发 NoneBot）
plugin_dir = project_root / "bpdiscord" / "plugins" / "bpdiscord"
ai_dir = plugin_dir / "ai"
memory_dir = ai_dir / "memory"

_create_stub_package("bpdiscord", [str(project_root / "bpdiscord")])
_create_stub_package("bpdiscord.plugins", [str(project_root / "bpdiscord" / "plugins")])
_create_stub_package("bpdiscord.plugins.bpdiscord", [str(plugin_dir)])
_create_stub_package("bpdiscord.plugins.bpdiscord.ai", [str(ai_dir)])
_create_stub_package("bpdiscord.plugins.bpdiscord.ai.memory", [str(memory_dir)])

# 2. 直接加载 config.py
try:
    config_module = _load_module_direct(
        "bpdiscord.plugins.bpdiscord.config",
        plugin_dir / "config.py",
        package_name="bpdiscord.plugins.bpdiscord",
    )
except Exception as e:
    print(f"\u274c 加载 config.py 失败: {e}")
    input("\n按回车键退出...")
    sys.exit(1)

# 3. 直接加载 knowledge_base.py
try:
    kb_module = _load_module_direct(
        "bpdiscord.plugins.bpdiscord.ai.memory.knowledge_base",
        memory_dir / "knowledge_base.py",
        package_name="bpdiscord.plugins.bpdiscord.ai.memory",
    )
    KnowledgeBaseMemory = kb_module.KnowledgeBaseMemory
except Exception as e:
    print(f"\u274c 加载 knowledge_base.py 失败: {e}")
    print("请确认新版插件架构文件完整：")
    print("  - bpdiscord/plugins/bpdiscord/config.py")
    print("  - bpdiscord/plugins/bpdiscord/ai/memory/knowledge_base.py")
    input("\n按回车键退出...")
    sys.exit(1)


# --- FAISSManager 层 ---
class FAISSManager:
    """知识库管理器 - 通过新版 KnowledgeBaseMemory 操作向量数据库"""

    def __init__(self):
        print("正在初始化向量数据库...")
        self.kb = KnowledgeBaseMemory()
        print("初始化完成！\n")

    def add_from_file(self, file_path: str):
        """从文本文件批量导入知识"""
        if not os.path.exists(file_path):
            return False, f"\u274c 错误：文件不存在 {file_path}"

        knowledge_list = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        knowledge_list.append(line)
        except Exception as e:
            return False, f"\u274c 读取文件失败: {e}"

        if not knowledge_list:
            return False, "\u26a0\ufe0f  文件内容为空"

        try:
            self.kb.add_knowledge_batch(knowledge_list)
            return True, f"\u2705 导入成功！共导入 {len(knowledge_list)} 条"
        except Exception as e:
            return False, f"\u274c 导入过程中发生错误: {e}"

    def search(self, query: str, k: int = 5):
        """检索知识"""
        try:
            result = self.kb.search_knowledge(query, k=k)
            if result == "未找到相关知识":
                return False, "未找到相关结果"
            return True, result
        except Exception as e:
            return False, f"检索出错: {e}"

    def list_all(self):
        """列出所有知识条目"""
        try:
            docs = self.kb.get_all_knowledge()
            if not docs:
                return False, "知识库为空"
            msg = f"总条数: {len(docs)}\n"
            for i, doc in enumerate(docs, 1):
                msg += f"[{i}] {doc.page_content}\n"
            return True, msg
        except Exception as e:
            return False, f"列出失败: {e}"

    def delete_by_index(self, index_str: str):
        """根据索引删除知识条目"""
        try:
            index = int(index_str)
            success = self.kb.delete_knowledge_by_index(index)
            if success:
                return True, f"\u2705 已删除索引 #{index} 的知识"
            else:
                return False, f"\u274c 索引 #{index} 不存在或删除失败"
        except ValueError:
            return False, "\u274c 请输入有效的数字"

    def delete_by_content(self, content: str):
        """根据内容删除知识条目"""
        try:
            success = self.kb.delete_knowledge_by_content(content)
            if success:
                return True, f"\u2705 已删除包含\u300c{content}\u300d的知识"
            else:
                return False, f"\u274c 未找到包含\u300c{content}\u300d的知识"
        except Exception as e:
            return False, f"\u274c 删除失败: {e}"

    def add_single(self, text: str):
        """添加单条知识"""
        if not text.strip():
            return False, "\u274c 内容不能为空"
        try:
            self.kb.add_knowledge(text.strip())
            return True, f"\u2705 已添加: {text.strip()}"
        except Exception as e:
            return False, f"\u274c 添加失败: {e}"

    def clear_knowledge_base(self):
        """清空知识库"""
        try:
            from langchain_community.vectorstores import FAISS
            self.kb.vectorstore = FAISS.from_texts(
                [""], self.kb.embeddings, metadatas=[{"__placeholder__": True}]
            )
            self.kb.vectorstore.save_local(self.kb.db_path)
            return True, "\u2705 知识库已清空"
        except Exception as e:
            return False, f"\u274c 清空知识库失败: {e}"

    def export(self, file_path: str):
        """导出知识库到文本文件"""
        try:
            docs = self.kb.get_all_knowledge()
            with open(file_path, "w", encoding="utf-8") as f:
                for doc in docs:
                    f.write(f"{doc.page_content}\n")
            return True, f"\u2705 导出成功，共 {len(docs)} 条数据"
        except Exception as e:
            return False, f"\u274c 导出失败: {e}"


# --- GUI 图形化界面 ---
class KnowledgeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("知识库管理工具 v2.1")
        self.root.geometry("950x650")

        self.manager = FAISSManager()

        style = ttk.Style()
        style.theme_use("clam")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.create_import_tab()
        self.create_search_tab()
        self.create_manage_tab()

        self.load_treeview_data()

    def create_import_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="导入知识")

        content = ttk.Frame(tab)
        content.pack(expand=True, fill="both", padx=20, pady=20)

        file_frame = ttk.LabelFrame(content, text="从文本文件导入")
        file_frame.pack(fill="x", pady=10)

        path_frame = ttk.Frame(file_frame)
        path_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(path_frame, text="文件路径:").grid(row=0, column=0, sticky="w", padx=5)
        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(path_frame, textvariable=self.path_var, width=50)
        path_entry.grid(row=0, column=1, padx=5)
        ttk.Button(path_frame, text="浏览...", command=self.browse_file).grid(row=0, column=2, padx=5)

        ttk.Button(file_frame, text="开始导入", command=self.start_import, width=20).pack(pady=10)

        manual_frame = ttk.LabelFrame(content, text="手动添加单条知识")
        manual_frame.pack(fill="x", pady=10)

        input_frame = ttk.Frame(manual_frame)
        input_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(input_frame, text="知识内容:").grid(row=0, column=0, sticky="w", padx=5)
        self.manual_var = tk.StringVar()
        manual_entry = ttk.Entry(input_frame, textvariable=self.manual_var, width=50)
        manual_entry.grid(row=0, column=1, padx=5)
        ttk.Button(input_frame, text="添加", command=self.add_manual, width=10).grid(row=0, column=2, padx=5)

        self.import_status_var = tk.StringVar()
        self.import_status_var.set("准备就绪")
        ttk.Label(content, textvariable=self.import_status_var, foreground="gray").pack(pady=5)

    def create_search_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="搜索知识")

        content = ttk.Frame(tab)
        content.pack(expand=True, fill="both", padx=20, pady=20)

        search_frame = ttk.Frame(content)
        search_frame.pack(fill="x", pady=10)

        ttk.Label(search_frame, text="查询内容:").grid(row=0, column=0, sticky="w", padx=5)
        self.query_var = tk.StringVar()
        query_entry = ttk.Entry(search_frame, textvariable=self.query_var, width=50)
        query_entry.grid(row=0, column=1, padx=5)
        ttk.Button(search_frame, text="搜索", command=self.perform_search, width=10).grid(row=0, column=2, padx=5)

        result_frame = ttk.LabelFrame(content, text="搜索结果")
        result_frame.pack(expand=True, fill="both", padx=10, pady=10)

        self.result_text = scrolledtext.ScrolledText(result_frame, wrap="word", font=("Consolas", 10))
        self.result_text.pack(expand=True, fill="both", padx=5, pady=5)

        self.search_status_var = tk.StringVar()
        self.search_status_var.set("等待搜索...")
        ttk.Label(content, textvariable=self.search_status_var, foreground="gray").pack(pady=5)

    def create_manage_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="管理知识")

        content = ttk.Frame(tab)
        content.pack(expand=True, fill="both", padx=10, pady=10)

        list_frame = ttk.LabelFrame(content, text="知识列表")
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ("index", "content")
        self.tree = ttk.Treeview(
            list_frame, columns=cols, show="headings", height=15, selectmode="extended"
        )
        self.tree.heading("index", text="索引")
        self.tree.column("index", width=80, anchor="center")
        self.tree.heading("content", text="内容")
        self.tree.column("content", width=650, anchor="w")

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

        btn_frame = ttk.Frame(content)
        btn_frame.pack(fill="x", pady=10)

        ttk.Button(btn_frame, text="删除选中", command=self.delete_item, width=15).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="批量删除选中", command=self.batch_delete_items, width=15).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="按内容删除", command=self.delete_by_content, width=15).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="清空知识库", command=self.clear_knowledge_base, width=15).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="导出全部", command=self.export_all, width=15).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="刷新列表", command=self.load_treeview_data, width=15).pack(side="left", padx=5)

        ttk.Label(
            content,
            text="提示：按住 Ctrl 可多选，或按 Shift 框选连续条目",
            foreground="gray",
            font=("Arial", 8),
        ).pack(pady=5)

        self.manage_status_var = tk.StringVar()
        self.manage_status_var.set("就绪")
        ttk.Label(content, textvariable=self.manage_status_var, foreground="gray").pack(pady=5)

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if filename:
            self.path_var.set(filename)

    def start_import(self):
        file_path = self.path_var.get()
        if not file_path:
            messagebox.showwarning("警告", "请选择一个文件！")
            return

        self.import_status_var.set("正在导入...")
        self.root.update()

        success, msg = self.manager.add_from_file(file_path)

        self.import_status_var.set(msg)
        if success:
            messagebox.showinfo("成功", msg)
            self.load_treeview_data()
        else:
            messagebox.showerror("错误", msg)

    def add_manual(self):
        text = self.manual_var.get()
        if not text.strip():
            messagebox.showwarning("警告", "请输入知识内容！")
            return

        success, msg = self.manager.add_single(text)
        self.import_status_var.set(msg)
        if success:
            self.manual_var.set("")
            self.load_treeview_data()
        else:
            messagebox.showerror("错误", msg)

    def perform_search(self):
        query = self.query_var.get()
        if not query:
            messagebox.showwarning("警告", "请输入搜索关键词！")
            return

        self.search_status_var.set("正在搜索...")
        self.root.update()

        success, msg = self.manager.search(query)

        if success:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, msg)
            self.search_status_var.set("找到相关结果")
        else:
            messagebox.showerror("错误", msg)
            self.result_text.delete(1.0, tk.END)

    def load_treeview_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        success, msg = self.manager.list_all()
        if success:
            lines = msg.split("\n")
            current_index = 1
            for line in lines:
                if line.strip().startswith("["):
                    content = line.split("]", 1)[1].strip()
                    self.tree.insert("", "end", values=(current_index, content))
                    current_index += 1

    def delete_item(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("警告", "请先在列表中选择一项！")
            return

        item = self.tree.item(selected_item)
        index_str = str(item["values"][0])

        self.manage_status_var.set("正在删除...")
        success, msg = self.manager.delete_by_index(index_str)

        if success:
            messagebox.showinfo("成功", msg)
            self.load_treeview_data()
        else:
            messagebox.showerror("错误", msg)
        self.manage_status_var.set("就绪")

    def batch_delete_items(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请先在列表中选择要删除的条目（按 Ctrl 或 Shift）！")
            return

        count = len(selected_items)
        confirm = messagebox.askyesno("确认批量删除", f"确定要删除选中的 {count} 条数据吗？")
        if not confirm:
            return

        success_count = 0
        fail_count = 0
        indices_to_delete = set()

        for item in selected_items:
            index_val = self.tree.item(item)["values"][0]
            indices_to_delete.add(index_val)

        for idx_str in indices_to_delete:
            success, msg = self.manager.delete_by_index(idx_str)
            if success:
                success_count += 1
            else:
                fail_count += 1

        self.load_treeview_data()

        result_msg = f"批量删除完成！成功删除 {success_count} 条"
        if fail_count > 0:
            result_msg += f" (有 {fail_count} 条因索引不存在而删除失败)"

        self.manage_status_var.set(result_msg)
        messagebox.showinfo("完成", result_msg)

    def delete_by_content(self):
        """按内容关键词删除知识条目"""
        dialog = tk.Toplevel(self.root)
        dialog.title("按内容删除")
        dialog.geometry("400x120")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="输入要删除的内容关键词:").pack(pady=5)
        content_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=content_var, width=40)
        entry.pack(pady=5)

        def do_delete():
            keyword = content_var.get().strip()
            if not keyword:
                messagebox.showwarning("警告", "请输入关键词！", parent=dialog)
                return
            confirm = messagebox.askyesno(
                "确认删除",
                f"将删除所有包含\u300c{keyword}\u300d的知识条目，确定吗？",
                parent=dialog,
            )
            if not confirm:
                return
            success, msg = self.manager.delete_by_content(keyword)
            dialog.destroy()
            if success:
                messagebox.showinfo("成功", msg)
                self.load_treeview_data()
            else:
                messagebox.showerror("错误", msg)
            self.manage_status_var.set("就绪")

        ttk.Button(dialog, text="删除", command=do_delete).pack(pady=10)

    def export_all(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text Files", "*.txt")]
        )
        if not file_path:
            return

        self.manage_status_var.set("正在导出...")
        success, msg = self.manager.export(file_path)

        if success:
            messagebox.showinfo("成功", msg)
        else:
            messagebox.showerror("错误", msg)
        self.manage_status_var.set("就绪")

    def clear_knowledge_base(self):
        confirm = messagebox.askyesno("确认清空", "确定要清空整个知识库吗？此操作不可恢复！")
        if not confirm:
            return

        self.manage_status_var.set("正在清空知识库...")
        self.root.update()

        success, msg = self.manager.clear_knowledge_base()

        if success:
            messagebox.showinfo("成功", msg)
            self.load_treeview_data()
        else:
            messagebox.showerror("错误", msg)

        self.manage_status_var.set("就绪")


# --- 启动 GUI ---
if __name__ == "__main__":
    root = tk.Tk()
    app = KnowledgeApp(root)
    root.mainloop()
