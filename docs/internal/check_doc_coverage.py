import ast
import os
import re
from pathlib import Path

py_files = sorted(Path('cloud/app/services/diagnosis').rglob('*.py'))
algo_md_files = [p.as_posix() for p in Path('docs/algorithms').rglob('*.md')]

def extract_signatures(py_path):
    text = open(py_path, encoding='utf-8').read()
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return {'error': str(e)}
    
    items = []
    
    def process_function(node, prefix=""):
        name = prefix + node.name
        args = []
        defaults_start = len(node.args.args) - len(node.args.defaults)
        for i, arg in enumerate(node.args.args):
            arg_name = arg.arg
            arg_type = ast.unparse(arg.annotation) if arg.annotation else None
            default = None
            if i >= defaults_start:
                default = ast.unparse(node.args.defaults[i - defaults_start])
            args.append((arg_name, arg_type, default))
        
        if node.args.vararg:
            v = node.args.vararg
            args.append((f'*{v.arg}', ast.unparse(v.annotation) if v.annotation else None, None))
        if node.args.kwarg:
            k = node.args.kwarg
            args.append((f'**{k.arg}', ast.unparse(k.annotation) if k.annotation else None, None))
        
        returns = ast.unparse(node.returns) if node.returns else None
        return {
            'type': 'method' if prefix else 'function',
            'name': name,
            'short_name': node.name,
            'args': args,
            'returns': returns,
            'lineno': node.lineno
        }
    
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            items.append(process_function(node))
        elif isinstance(node, ast.ClassDef):
            items.append({
                'type': 'class',
                'name': node.name,
                'lineno': node.lineno
            })
            for body_node in node.body:
                if isinstance(body_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    items.append(process_function(body_node, prefix=node.name + "."))
    
    return items

def name_in_md(text, item):
    name = item['name']
    patterns = [
        rf'\b{re.escape(name)}\b',
        rf'`{re.escape(name)}`',
        rf'##+\s*{re.escape(name)}',
    ]
    if any(re.search(p, text) for p in patterns):
        return True
    
    # For Class.method, check if class section contains method short name
    if item['type'] == 'method' and '.' in name:
        class_name = name.split('.')[0]
        short = item['short_name']
        # Split by markdown headers
        sections = re.split(r'\n(?=#{1,4}\s)', text)
        for sec in sections:
            # If section header contains class name
            if re.search(rf'#{1,4}\s+`?{re.escape(class_name)}`?\b', sec):
                # Check if short name appears in this section
                if re.search(rf'\b{re.escape(short)}\b', sec):
                    return True
            # Also check if there's a general class section and method is in a subsection
        # Fallback: if both class and short name appear anywhere
        if re.search(rf'\b{re.escape(class_name)}\b', text) and re.search(rf'\b{re.escape(short)}\b', text):
            return True
    
    return False

def check_md(md_path, items):
    if not os.path.exists(md_path):
        return {'exists': False, 'covered': [], 'missing': items, 'type_missing': items, 'link': False}
    text = open(md_path, encoding='utf-8').read()
    covered = []
    missing = []
    type_missing = []
    for it in items:
        found = name_in_md(text, it)
        if found:
            covered.append(it)
            has_type_info = False
            if it.get('returns'):
                if it['returns'] in text:
                    has_type_info = True
                elif re.search(r'返回|返回值|输出|->', text):
                    has_type_info = True
            if it.get('args'):
                for arg_name, arg_type, _ in it['args']:
                    if arg_type and (arg_type in text or re.search(rf'{re.escape(arg_name)}\s*[:：]', text)):
                        has_type_info = True
                        break
            has_hints = bool(it.get('returns') or any(a[1] for a in it.get('args', [])))
            if not has_type_info and has_hints:
                type_missing.append(it)
        else:
            missing.append(it)
    has_link = any(algo in text for algo in algo_md_files) or 'algorithms/' in text or 'wavelet_and_modality_decomposition' in text
    return {'exists': True, 'covered': covered, 'missing': missing, 'type_missing': type_missing, 'link': has_link}

reports = []
total_py = 0
total_items = 0
total_covered = 0
total_missing = 0

for py_file in py_files:
    rel = py_file.relative_to('cloud/app/services/diagnosis').as_posix()
    md_rel = Path(rel).with_suffix('.md')
    md_path = Path('docs/backend/app/services/diagnosis') / md_rel
    items = extract_signatures(str(py_file))
    if 'error' in items:
        reports.append((str(rel), {'error': items['error']}, []))
        continue
    result = check_md(str(md_path), items)
    reports.append((str(rel), result, items))
    total_py += 1
    total_items += len(items)
    total_covered += len(result['covered'])
    total_missing += len(result['missing'])

with open('doc_coverage_report.md', 'w', encoding='utf-8') as f:
    for rel_str, result, items in reports:
        if 'error' in result:
            f.write(f'### 文件: services/diagnosis/{rel_str}\n')
            f.write(f'- **状态**: 解析错误 - {result["error"]}\n')
            f.write('\n')
            continue
        status = '完整'
        if not result['exists']:
            status = '文档缺失'
        elif result['missing']:
            status = '部分缺失'
        elif result['type_missing']:
            status = '类型注解缺失'
        
        covered_names = [it['name'] for it in result['covered']]
        missing_sigs = []
        for it in result['missing']:
            sig = f"{it['name']}({', '.join([a[0] + (':' + a[1] if a[1] else '') for a in it['args']])})" + (f" -> {it['returns']}" if it['returns'] else '')
            missing_sigs.append(sig)
        type_missing_names = [it['name'] for it in result['type_missing']]
        md_name = Path(rel_str).with_suffix('.md').as_posix()
        f.write(f'### 文件: services/diagnosis/{rel_str} -> docs/backend/app/services/diagnosis/{md_name}\n')
        f.write(f'- **状态**: {status}\n')
        f.write(f'- **已覆盖函数/类**: {covered_names}\n')
        f.write(f'- **缺失函数/类**: {missing_sigs}\n')
        f.write(f'- **类型注解缺失**: {type_missing_names}\n')
        f.write(f'- **算法文档链接**: {"有" if result["link"] else "无"}\n')
        f.write('\n')
    
    f.write('---\n')
    f.write('**统计总结**:\n')
    f.write(f'- Python 文件总数: {total_py}\n')
    f.write(f'- 函数/类/方法总数: {total_items}\n')
    f.write(f'- 已覆盖数: {total_covered}\n')
    f.write(f'- 缺失数: {total_missing}\n')
    f.write(f'- 覆盖率: {total_covered/total_items*100:.1f}%\n')
    f.write(f'- 文档缺失文件数: {sum(1 for _,r,_ in reports if not r.get("exists", True))}\n')

print("Report written to doc_coverage_report.md")
