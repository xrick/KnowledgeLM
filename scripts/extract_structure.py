import ast
import os


def analyze_file_structure(file_path):
    """
    分析 Python 檔案並提取類別、函式 (含 Async) 和頂層常數。
    """
    if not os.path.exists(file_path):
        print(f"錯誤: 找不到檔案 {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        file_content = f.read()

    try:
        tree = ast.parse(file_content)
    except SyntaxError as e:
        print(f"語法錯誤，無法解析: {e}")
        return

    print(f"# Structure Analysis of: {os.path.basename(file_path)}\n")
    print("---")

    # 遞迴函數來處理節點
    def visit_nodes(nodes, indent_level=0):
        indent = "  " * indent_level

        for node in nodes:
            # 1. 處理函式 (FunctionDef & AsyncFunctionDef)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = (
                    "ASYNC DEF" if isinstance(node, ast.AsyncFunctionDef) else "DEF"
                )
                # 嘗試提取 docstring 的第一行
                docstring = ast.get_docstring(node)
                doc_summary = f" # {docstring.split(chr(10))[0]}" if docstring else ""

                print(
                    f"{indent}- [{prefix}] {node.name}(...): (Line {node.lineno}){doc_summary}"
                )

                # 如果是內狀函式 (Nested functions)，可以選擇是否要遞迴
                # 這裡我們只對 Class 內的 method 做遞迴，避免過於複雜

            # 2. 處理類別 (ClassDef)
            elif isinstance(node, ast.ClassDef):
                docstring = ast.get_docstring(node)
                doc_summary = f" # {docstring.split(chr(10))[0]}" if docstring else ""

                print(
                    f"{indent}- [CLASS] {node.name}: (Line {node.lineno}){doc_summary}"
                )
                # 深入類別內部抓取 methods
                visit_nodes(node.body, indent_level + 1)

            # 3. 處理頂層常數 (Assignments) - 簡單過濾全大寫變數
            elif isinstance(node, ast.Assign) and indent_level == 0:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        # 這裡只抓全大寫的常數 (CONSTANTS)
                        print(f"{indent}- [CONST] {target.id} (Line {node.lineno})")

    visit_nodes(tree.body)


# --- 使用設定 ---
# 請將下方的路徑改為你的目標檔案路徑
TARGET_FILE = "app/api/v1/endpoints/skills.py"

# 為了方便測試，如果沒有該檔案，你可以建立一個假的 .py 檔測試，或直接修改上面的路徑
if __name__ == "__main__":
    # 如果路徑不存在，這裡提示使用者修改
    if TARGET_FILE == "app/api/v1/endpoints/skills.py" and not os.path.exists(
        TARGET_FILE
    ):
        print(f"請編輯腳本中的 `TARGET_FILE` 變數，將其指向你的真實檔案位置。")
        print(f"目前設定路徑: {TARGET_FILE}")
    else:
        analyze_file_structure(TARGET_FILE)
