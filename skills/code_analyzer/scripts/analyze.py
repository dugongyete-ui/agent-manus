"""Code Analyzer - Menganalisis kode sumber."""

import os
import re
import logging

logger = logging.getLogger(__name__)

LANG_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "React JSX", ".tsx": "React TSX",
    ".java": "Java", ".cpp": "C++", ".c": "C",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
    ".html": "HTML", ".css": "CSS", ".sql": "SQL",
    ".sh": "Shell", ".bash": "Bash",
    ".yaml": "YAML", ".yml": "YAML", ".json": "JSON",
    ".md": "Markdown", ".xml": "XML",
}

COMMENT_PATTERNS = {
    "Python": (r'#.*$', r'"""[\s\S]*?"""', r"'''[\s\S]*?'''"),
    "JavaScript": (r'//.*$', r'/\*[\s\S]*?\*/'),
    "TypeScript": (r'//.*$', r'/\*[\s\S]*?\*/'),
    "Java": (r'//.*$', r'/\*[\s\S]*?\*/'),
    "C++": (r'//.*$', r'/\*[\s\S]*?\*/'),
    "C": (r'//.*$', r'/\*[\s\S]*?\*/'),
    "Go": (r'//.*$', r'/\*[\s\S]*?\*/'),
    "Ruby": (r'#.*$', r'=begin[\s\S]*?=end'),
    "Shell": (r'#.*$',),
}


def detect_language(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return LANG_EXTENSIONS.get(ext, "Unknown")


def count_lines(content: str) -> dict:
    lines = content.split("\n")
    total = len(lines)
    blank = sum(1 for line in lines if not line.strip())
    code = total - blank
    return {"total": total, "code": code, "blank": blank}


def find_functions(content: str, language: str) -> list[str]:
    patterns = {
        "Python": r'def\s+(\w+)\s*\(',
        "JavaScript": r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function))',
        "TypeScript": r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function))',
        "Java": r'(?:public|private|protected|static)\s+\w+\s+(\w+)\s*\(',
        "Go": r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(',
        "Ruby": r'def\s+(\w+)',
    }
    pattern = patterns.get(language)
    if not pattern:
        return []
    matches = re.findall(pattern, content)
    funcs = []
    for m in matches:
        if isinstance(m, tuple):
            funcs.append(next((x for x in m if x), ""))
        else:
            funcs.append(m)
    return [f for f in funcs if f]


def find_classes(content: str, language: str) -> list[str]:
    patterns = {
        "Python": r'class\s+(\w+)',
        "JavaScript": r'class\s+(\w+)',
        "TypeScript": r'(?:class|interface)\s+(\w+)',
        "Java": r'class\s+(\w+)',
    }
    pattern = patterns.get(language)
    if not pattern:
        return []
    return re.findall(pattern, content)


def find_imports(content: str, language: str) -> list[str]:
    patterns = {
        "Python": r'(?:import\s+(\S+)|from\s+(\S+)\s+import)',
        "JavaScript": r'(?:import\s+.*?from\s+[\'"](.+?)[\'"]|require\([\'"](.+?)[\'"]\))',
        "TypeScript": r'import\s+.*?from\s+[\'"](.+?)[\'"]',
        "Go": r'import\s+["\(]([^"\)]+)',
    }
    pattern = patterns.get(language)
    if not pattern:
        return []
    matches = re.findall(pattern, content)
    imports = []
    for m in matches:
        if isinstance(m, tuple):
            imports.append(next((x for x in m if x), ""))
        else:
            imports.append(m)
    return [i for i in imports if i]


def count_comments(content: str, language: str) -> int:
    patterns = COMMENT_PATTERNS.get(language, ())
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, content, re.MULTILINE))
    return count


def analyze_complexity(content: str, language: str) -> dict:
    branch_keywords = {
        "Python": r'\b(if|elif|for|while|except|and|or)\b',
        "JavaScript": r'\b(if|else if|for|while|catch|switch|case|&&|\|\|)\b',
    }
    pattern = branch_keywords.get(language, r'\b(if|for|while)\b')
    branches = len(re.findall(pattern, content))

    lines = content.split("\n")
    max_indent = 0
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            if language == "Python":
                indent = indent // 4
            else:
                indent = indent // 2
            max_indent = max(max_indent, indent)

    return {
        "branch_count": branches,
        "max_nesting": max_indent,
        "complexity_score": "low" if branches < 10 else "medium" if branches < 30 else "high",
    }


def main(**kwargs) -> dict:
    file_path = kwargs.get("file_path", "")
    content = kwargs.get("content", "")

    if file_path and os.path.exists(file_path):
        with open(file_path, "r", errors="ignore") as f:
            content = f.read()
    elif not content:
        return {"success": False, "error": "file_path atau content diperlukan"}

    language = detect_language(file_path) if file_path else "Unknown"
    line_stats = count_lines(content)
    functions = find_functions(content, language)
    classes = find_classes(content, language)
    imports = find_imports(content, language)
    comment_count = count_comments(content, language)
    complexity = analyze_complexity(content, language)

    code_lines = line_stats["code"]
    comment_ratio = round(comment_count / max(code_lines, 1) * 100, 1)

    suggestions = []
    if comment_ratio < 5:
        suggestions.append("Tambahkan lebih banyak komentar untuk meningkatkan keterbacaan")
    if complexity["complexity_score"] == "high":
        suggestions.append("Pertimbangkan untuk memecah fungsi yang kompleks menjadi bagian lebih kecil")
    if complexity["max_nesting"] > 5:
        suggestions.append("Nesting terlalu dalam, pertimbangkan early return atau refactoring")
    if len(functions) > 20:
        suggestions.append("File memiliki banyak fungsi, pertimbangkan untuk memisahkan ke modul berbeda")

    return {
        "success": True,
        "file_path": file_path,
        "language": language,
        "lines": line_stats,
        "functions": {"count": len(functions), "names": functions[:20]},
        "classes": {"count": len(classes), "names": classes[:10]},
        "imports": {"count": len(imports), "names": imports[:20]},
        "comments": {"count": comment_count, "ratio_percent": comment_ratio},
        "complexity": complexity,
        "suggestions": suggestions,
    }


def run(**kwargs):
    return main(**kwargs)


if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) > 1:
        result = main(file_path=sys.argv[1])
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Penggunaan: python analyze.py <file_path>")
