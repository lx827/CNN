import ast
import os
import re
from pathlib import Path

API_DIR = Path("D:/code/CNN/cloud/app/api")
DOCS_DIR = Path("D:/code/CNN/docs/backend/app/api")
ALGO_DIR = Path("D:/code/CNN/docs/algorithms")

# 算法相关文件
ALGO_FILES = {"gear.py", "envelope.py", "order.py", "cepstrum.py", "diagnosis_ops.py"}

def get_type_hint_str(node):
    """将 AST 注解节点转换为字符串"""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Attribute):
            return f"{get_type_hint_str(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            return f"{get_type_hint_str(node.value)}[{get_type_hint_str(node.slice)}]"
        elif isinstance(node, ast.List):
            return "[" + ", ".join(get_type_hint_str(e) for e in node.elts) + "]"
        elif isinstance(node, ast.Tuple):
            return "(" + ", ".join(get_type_hint_str(e) for e in node.elts) + ")"
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return f"{get_type_hint_str(node.left)} | {get_type_hint_str(node.right)}"
        elif isinstance(node, ast.Expression):
            return get_type_hint_str(node.body)
        elif isinstance(node, ast.Index):
            return get_type_hint_str(node.value)
        else:
            return None

def extract_defs(py_path):
    """从 .py 文件中提取函数和类定义"""
    with open(py_path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)

    results = {
        "functions": [],  # list of dict
        "classes": [],    # list of dict with methods
    }

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = {
                "name": node.name,
                "args": [],
                "returns": get_type_hint_str(node.returns),
                "lineno": node.lineno,
            }
            for arg in node.args.args:
                arg_name = arg.arg
                arg_type = get_type_hint_str(arg.annotation)
                func_info["args"].append((arg_name, arg_type))
            # defaults offset
            defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + [ast.unparse(d) for d in node.args.defaults]
            results["functions"].append(func_info)

        elif isinstance(node, ast.ClassDef):
            class_info = {
                "name": node.name,
                "methods": [],
                "lineno": node.lineno,
            }
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_info = {
                        "name": item.name,
                        "args": [],
                        "returns": get_type_hint_str(item.returns),
                        "lineno": item.lineno,
                    }
                    for arg in item.args.args:
                        arg_name = arg.arg
                        arg_type = get_type_hint_str(arg.annotation)
                        method_info["args"].append((arg_name, arg_type))
                    class_info["methods"].append(method_info)
            results["classes"].append(class_info)

    return results

def check_md_coverage(md_path, py_defs):
    """检查 md 文件是否覆盖了 py 中的定义"""
    if not md_path.exists():
        return {
            "exists": False,
            "covered_functions": [],
            "missing_functions": py_defs["functions"],
            "missing_classes": py_defs["classes"],
            "type_hint_missing": [],
            "algo_link": False,
        }

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    covered_functions = []
    missing_functions = []
    type_hint_missing = []

    for func in py_defs["functions"]:
        name = func["name"]
        if name in md_content:
            covered_functions.append(name)
            # 检查参数列表
            has_args = len(func["args"]) == 0 or any(arg[0] in md_content for arg in func["args"])
            # 检查类型注解：仅当源码有注解时才检查 md 是否覆盖
            source_types = [arg[1] for arg in func["args"] if arg[1]] + ([func["returns"]] if func.get("returns") else [])
            type_hint_ok = True
            if source_types:
                type_hint_ok = all(t in md_content for t in source_types)
            # 检查返回类型
            return_ok = func.get("returns") is None or func["returns"] in md_content
            if not (has_args and type_hint_ok and return_ok):
                type_hint_missing.append(name)
        else:
            missing_functions.append(func)

    missing_classes = []
    for cls in py_defs["classes"]:
        name = cls["name"]
        if name not in md_content:
            missing_classes.append(cls)
        else:
            for method in cls["methods"]:
                mname = method["name"]
                full_sig = f"{name}.{mname}"
                if mname not in md_content:
                    missing_functions.append({**method, "class": name})
                else:
                    covered_functions.append(full_sig)
                    has_args = len(method["args"]) == 0 or any(arg[0] in md_content for arg in method["args"])
                    source_types = [arg[1] for arg in method["args"] if arg[1]] + ([method["returns"]] if method.get("returns") else [])
                    type_hint_ok = True
                    if source_types:
                        type_hint_ok = all(t in md_content for t in source_types)
                    return_ok = method.get("returns") is None or method["returns"] in md_content
                    if not (has_args and type_hint_ok and return_ok):
                        type_hint_missing.append(full_sig)

    # 算法链接检查：检查是否链接到 docs/algorithms/
    algo_link = bool(re.search(r'\.\./algorithms/|docs/algorithms/|/algorithms/', md_content))

    return {
        "exists": True,
        "covered_functions": covered_functions,
        "missing_functions": missing_functions,
        "missing_classes": missing_classes,
        "type_hint_missing": type_hint_missing,
        "algo_link": algo_link,
    }

def format_signature(item, is_class=False):
    if is_class:
        return f"class {item['name']}"
    name = item["name"]
    args = ", ".join([f"{a[0]}: {a[1]}" if a[1] else a[0] for a in item["args"]])
    ret = f" -> {item['returns']}" if item.get("returns") else ""
    if "class" in item:
        return f"{item['class']}.{name}({args}){ret}"
    return f"{name}({args}){ret}"

def main():
    import sys
    out_path = Path("D:/code/CNN/check_api_docs_report.md")
    with open(out_path, "w", encoding="utf-8") as out:
        sys.stdout = out
        py_files = sorted(API_DIR.rglob("*.py"))
        total_files = 0
        complete = 0
        partial = 0
        missing = 0
        algo_linked = 0
        algo_total = 0

        for py_path in py_files:
            rel = py_path.relative_to(API_DIR)
            md_path = DOCS_DIR / rel.with_suffix(".md")

            py_defs = extract_defs(py_path)
            result = check_md_coverage(md_path, py_defs)

            is_algo = rel.name in ALGO_FILES
            if is_algo:
                algo_total += 1
                if result["algo_link"]:
                    algo_linked += 1

            has_missing = bool(result["missing_functions"] or result["missing_classes"])
            if not result["exists"]:
                status = "文档缺失"
                missing += 1
            elif has_missing:
                status = "部分缺失"
                partial += 1
            else:
                status = "完整"
                complete += 1

            total_files += 1

            rel_str = str(rel).replace("\\", "/")
            print(f"### 文件: api/{rel_str} -> docs/backend/app/api/{rel_str[:-3]}.md")
            print(f"- **状态**: {status}")
            print(f"- **已覆盖函数/方法**: {result['covered_functions'] if result['covered_functions'] else '[]'}")
            missing_sigs = []
            for f in result["missing_functions"]:
                missing_sigs.append(format_signature(f))
            for c in result["missing_classes"]:
                missing_sigs.append(format_signature(c, is_class=True))
            print(f"- **缺失函数/类**: {missing_sigs if missing_sigs else '[]'}")
            print(f"- **类型注解缺失**: {result['type_hint_missing'] if result['type_hint_missing'] else '[]'}")
            if is_algo:
                print(f"- **算法链接**: {'有' if result['algo_link'] else '无'}")
            else:
                print(f"- **算法链接**: 不适用")
            print()

        print("---")
        print("### 统计总结")
        print(f"- **总文件数**: {total_files}")
        print(f"- **完整**: {complete}")
        print(f"- **部分缺失**: {partial}")
        print(f"- **文档缺失**: {missing}")
        print(f"- **算法文件总数**: {algo_total}")
        print(f"- **算法文件有链接**: {algo_linked}")
        sys.stdout = sys.__stdout__

if __name__ == "__main__":
    main()
