"""WebDev Tool - Inisialisasi proyek web, iterasi kode, dan ekspor zip."""

import asyncio
import json
import logging
import os
import shutil
import time
import zipfile
from typing import Optional

logger = logging.getLogger(__name__)


FRAMEWORK_TEMPLATES = {
    "react": {
        "files": {
            "package.json": json.dumps({
                "name": "app",
                "version": "1.0.0",
                "private": True,
                "scripts": {
                    "dev": "react-scripts start",
                    "build": "react-scripts build",
                    "test": "react-scripts test",
                },
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                    "react-scripts": "5.0.1",
                },
            }, indent=2),
            "src/App.js": 'import React from "react";\n\nexport default function App() {\n  return (\n    <div className="App">\n      <h1>Hello React</h1>\n    </div>\n  );\n}\n',
            "src/index.js": 'import React from "react";\nimport ReactDOM from "react-dom/client";\nimport App from "./App";\n\nconst root = ReactDOM.createRoot(document.getElementById("root"));\nroot.render(<App />);\n',
            "public/index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>React App</title>\n</head>\n<body>\n  <div id="root"></div>\n</body>\n</html>\n',
        },
        "dependencies": ["react", "react-dom", "react-scripts"],
        "manager": "npm",
        "dev_command": "npm start",
        "build_command": "npm run build",
    },
    "vue": {
        "files": {
            "package.json": json.dumps({
                "name": "app",
                "version": "1.0.0",
                "private": True,
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {"vue": "^3.3.0"},
                "devDependencies": {"@vitejs/plugin-vue": "^4.0.0", "vite": "^5.0.0"},
            }, indent=2),
            "src/App.vue": '<template>\n  <div id="app">\n    <h1>Hello Vue</h1>\n  </div>\n</template>\n\n<script>\nexport default {\n  name: "App",\n};\n</script>\n',
            "src/main.js": 'import { createApp } from "vue";\nimport App from "./App.vue";\n\ncreateApp(App).mount("#app");\n',
            "index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>Vue App</title>\n</head>\n<body>\n  <div id="app"></div>\n  <script type="module" src="/src/main.js"></script>\n</body>\n</html>\n',
            "vite.config.js": 'import { defineConfig } from "vite";\nimport vue from "@vitejs/plugin-vue";\n\nexport default defineConfig({\n  plugins: [vue()],\n});\n',
        },
        "dependencies": ["vue"],
        "manager": "npm",
        "dev_command": "npm run dev",
        "build_command": "npm run build",
    },
    "flask": {
        "files": {
            "app.py": 'from flask import Flask, render_template, jsonify\n\napp = Flask(__name__)\n\n\n@app.route("/")\ndef index():\n    return render_template("index.html")\n\n\n@app.route("/api/health")\ndef health():\n    return jsonify({"status": "ok"})\n\n\nif __name__ == "__main__":\n    app.run(host="0.0.0.0", port=5000, debug=True)\n',
            "templates/index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>Flask App</title>\n</head>\n<body>\n  <h1>Hello Flask</h1>\n</body>\n</html>\n',
            "requirements.txt": "flask>=3.0.0\ngunicorn>=21.2.0\n",
        },
        "dependencies": ["flask", "gunicorn"],
        "manager": "pip",
        "dev_command": "python app.py",
        "build_command": None,
    },
    "express": {
        "files": {
            "package.json": json.dumps({
                "name": "app",
                "version": "1.0.0",
                "scripts": {
                    "start": "node server.js",
                    "dev": "node --watch server.js",
                },
                "dependencies": {"express": "^4.18.0"},
            }, indent=2),
            "server.js": 'const express = require("express");\nconst path = require("path");\n\nconst app = express();\nconst PORT = process.env.PORT || 5000;\n\napp.use(express.json());\napp.use(express.static("public"));\n\napp.get("/api/health", (req, res) => {\n  res.json({ status: "ok" });\n});\n\napp.get("/", (req, res) => {\n  res.sendFile(path.join(__dirname, "public", "index.html"));\n});\n\napp.listen(PORT, "0.0.0.0", () => {\n  console.log(`Server running on port ${PORT}`);\n});\n',
            "public/index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>Express App</title>\n</head>\n<body>\n  <h1>Hello Express</h1>\n</body>\n</html>\n',
        },
        "dependencies": ["express"],
        "manager": "npm",
        "dev_command": "npm run dev",
        "build_command": None,
    },
    "nextjs": {
        "files": {
            "package.json": json.dumps({
                "name": "app",
                "version": "1.0.0",
                "private": True,
                "scripts": {
                    "dev": "next dev",
                    "build": "next build",
                    "start": "next start",
                },
                "dependencies": {
                    "next": "^14.0.0",
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                },
            }, indent=2),
            "app/page.js": 'export default function Home() {\n  return (\n    <main>\n      <h1>Hello Next.js</h1>\n    </main>\n  );\n}\n',
            "app/layout.js": 'export const metadata = {\n  title: "Next.js App",\n  description: "Created with Next.js",\n};\n\nexport default function RootLayout({ children }) {\n  return (\n    <html lang="en">\n      <body>{children}</body>\n    </html>\n  );\n}\n',
        },
        "dependencies": ["next", "react", "react-dom"],
        "manager": "npm",
        "dev_command": "npm run dev",
        "build_command": "npm run build",
    },
    "fastapi": {
        "files": {
            "main.py": 'from fastapi import FastAPI\nfrom fastapi.responses import HTMLResponse\n\napp = FastAPI()\n\n\n@app.get("/", response_class=HTMLResponse)\nasync def root():\n    return "<h1>Hello FastAPI</h1>"\n\n\n@app.get("/api/health")\nasync def health():\n    return {"status": "ok"}\n',
            "requirements.txt": "fastapi>=0.100.0\nuvicorn[standard]>=0.23.0\n",
        },
        "dependencies": ["fastapi", "uvicorn[standard]"],
        "manager": "pip",
        "dev_command": "uvicorn main:app --host 0.0.0.0 --port 5000 --reload",
        "build_command": None,
    },
}


class WebDevTool:
    def __init__(self, default_port: int = 5000):
        self.default_port = default_port
        self.projects: list[dict] = []

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        return (
            f"WebDev tool siap. Intent: {intent}. "
            f"Framework tersedia: {', '.join(FRAMEWORK_TEMPLATES.keys())}. "
            f"Gunakan init_project() untuk memulai proyek baru."
        )

    def init_project(self, name: str, framework: str, output_dir: str = ".") -> dict:
        if framework not in FRAMEWORK_TEMPLATES:
            return {
                "success": False,
                "error": f"Framework '{framework}' tidak didukung. Pilih: {list(FRAMEWORK_TEMPLATES.keys())}",
            }

        template = FRAMEWORK_TEMPLATES[framework]
        project_dir = os.path.join(output_dir, name)
        os.makedirs(project_dir, exist_ok=True)

        created_files = []
        for file_path, content in template["files"].items():
            full_path = os.path.join(project_dir, file_path)
            os.makedirs(os.path.dirname(full_path) or project_dir, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            created_files.append(file_path)

        gitignore_content = self._generate_gitignore(framework)
        gitignore_path = os.path.join(project_dir, ".gitignore")
        with open(gitignore_path, "w") as f:
            f.write(gitignore_content)
        created_files.append(".gitignore")

        project_info = {
            "name": name,
            "framework": framework,
            "directory": project_dir,
            "files": created_files,
            "dependencies": template.get("dependencies", []),
            "manager": template.get("manager", "npm"),
            "dev_command": template.get("dev_command"),
            "build_command": template.get("build_command"),
        }
        self.projects.append(project_info)
        logger.info(f"Proyek '{name}' diinisialisasi dengan {framework}")

        return {"success": True, "project": project_info}

    async def install_dependencies(self, project_dir: str, manager: str = "npm") -> dict:
        try:
            if manager == "npm":
                cmd = "npm install"
            elif manager == "yarn":
                cmd = "yarn install"
            elif manager == "pip":
                req_file = os.path.join(project_dir, "requirements.txt")
                if os.path.exists(req_file):
                    cmd = f"pip install -r {req_file}"
                else:
                    return {"success": False, "error": "requirements.txt tidak ditemukan"}
            else:
                return {"success": False, "error": f"Manager tidak didukung: {manager}"}

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            success = process.returncode == 0

            return {
                "success": success,
                "manager": manager,
                "output": stdout.decode("utf-8", errors="replace")[:3000],
                "errors": stderr.decode("utf-8", errors="replace")[:1000] if not success else None,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "Instalasi timeout (300s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def add_dependency(self, project_dir: str, packages: list[str], manager: str = "npm", dev: bool = False) -> dict:
        try:
            if manager == "npm":
                flag = "--save-dev" if dev else ""
                cmd = f"npm install {flag} {' '.join(packages)}".strip()
            elif manager == "pip":
                cmd = f"pip install {' '.join(packages)}"
            elif manager == "yarn":
                flag = "--dev" if dev else ""
                cmd = f"yarn add {flag} {' '.join(packages)}".strip()
            else:
                return {"success": False, "error": f"Manager tidak didukung: {manager}"}

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            success = process.returncode == 0

            return {
                "success": success,
                "packages": packages,
                "output": stdout.decode("utf-8", errors="replace")[:2000],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def run_dev_server(self, project_dir: str, framework: str) -> dict:
        template = FRAMEWORK_TEMPLATES.get(framework)
        if not template:
            return {"success": False, "error": f"Framework tidak dikenal: {framework}"}

        dev_cmd = template.get("dev_command")
        if not dev_cmd:
            return {"success": False, "error": f"Tidak ada perintah dev untuk {framework}"}

        try:
            process = await asyncio.create_subprocess_shell(
                dev_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            return {
                "success": True,
                "pid": process.pid,
                "command": dev_cmd,
                "message": f"Dev server dimulai: {dev_cmd} (PID: {process.pid})",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def build_project(self, project_dir: str, framework: str) -> dict:
        template = FRAMEWORK_TEMPLATES.get(framework)
        if not template:
            return {"success": False, "error": f"Framework tidak dikenal: {framework}"}

        build_cmd = template.get("build_command")
        if not build_cmd:
            return {"success": True, "message": f"Framework {framework} tidak memerlukan build"}

        try:
            process = await asyncio.create_subprocess_shell(
                build_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            success = process.returncode == 0

            return {
                "success": success,
                "command": build_cmd,
                "output": stdout.decode("utf-8", errors="replace")[:3000],
                "errors": stderr.decode("utf-8", errors="replace")[:1000] if not success else None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generate_gitignore(self, framework: str) -> str:
        common = "node_modules/\n.env\n.env.local\n*.log\n.DS_Store\n__pycache__/\n*.pyc\n.venv/\n"
        extra = {
            "react": "build/\n.react-scripts/\n",
            "vue": "dist/\n.vite/\n",
            "flask": "*.pyc\ninstance/\n.webassets-cache\n",
            "express": "dist/\n",
            "nextjs": ".next/\nout/\n",
            "fastapi": "*.pyc\n.mypy_cache/\n",
        }
        return common + extra.get(framework, "")

    def list_frameworks(self) -> list[dict]:
        result = []
        for name, template in FRAMEWORK_TEMPLATES.items():
            result.append({
                "name": name,
                "manager": template.get("manager", "unknown"),
                "dev_command": template.get("dev_command"),
                "dependencies": template.get("dependencies", []),
            })
        return result

    def get_project_structure(self, project_dir: str) -> dict:
        structure = {"directories": [], "files": []}
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", ".next", ".venv")]
            rel_root = os.path.relpath(root, project_dir)
            for d in dirs:
                structure["directories"].append(os.path.join(rel_root, d))
            for f in files:
                structure["files"].append(os.path.join(rel_root, f))
        return structure

    def export_zip(self, project_dir: str, output_path: Optional[str] = None,
                   exclude_patterns: Optional[list[str]] = None) -> dict:
        if not os.path.exists(project_dir):
            return {"success": False, "error": f"Direktori tidak ditemukan: {project_dir}"}

        exclude = set(exclude_patterns or ["node_modules", ".git", "__pycache__", ".next", ".venv", ".env"])

        if not output_path:
            proj_name = os.path.basename(project_dir)
            output_path = os.path.join(self.output_dir, f"{proj_name}_{int(time.time())}.zip")
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            files_added = 0
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(project_dir):
                    dirs[:] = [d for d in dirs if d not in exclude]
                    for f in files:
                        if f in exclude:
                            continue
                        full_path = os.path.join(root, f)
                        arc_name = os.path.relpath(full_path, project_dir)
                        try:
                            zf.write(full_path, arc_name)
                            files_added += 1
                        except Exception:
                            pass

            size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 2)
            logger.info(f"Proyek diekspor ke zip: {output_path} ({files_added} files, {size_mb}MB)")

            return {
                "success": True,
                "output_path": output_path,
                "files_count": files_added,
                "size_mb": size_mb,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_file(self, project_dir: str, file_path: str) -> dict:
        full_path = os.path.join(project_dir, file_path)
        if not os.path.exists(full_path):
            return {"success": False, "error": f"File tidak ditemukan: {file_path}"}
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "file_path": file_path, "content": content, "size": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, project_dir: str, file_path: str, content: str) -> dict:
        full_path = os.path.join(project_dir, file_path)
        try:
            os.makedirs(os.path.dirname(full_path) or project_dir, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"File ditulis: {file_path}")
            return {"success": True, "file_path": file_path, "size": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def edit_file(self, project_dir: str, file_path: str,
                  old_text: str, new_text: str) -> dict:
        full_path = os.path.join(project_dir, file_path)
        if not os.path.exists(full_path):
            return {"success": False, "error": f"File tidak ditemukan: {file_path}"}
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_text not in content:
                return {"success": False, "error": "Teks lama tidak ditemukan dalam file"}

            new_content = content.replace(old_text, new_text, 1)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            logger.info(f"File diedit: {file_path}")
            return {"success": True, "file_path": file_path, "changes": 1}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_component(self, project_dir: str, name: str, framework: str,
                         template_type: str = "functional") -> dict:
        component_templates = {
            "react": {
                "functional": f'import React from "react";\n\nexport default function {name}() {{\n  return (\n    <div className="{name.lower()}">\n      <h2>{name}</h2>\n    </div>\n  );\n}}\n',
                "class": f'import React, {{ Component }} from "react";\n\nexport default class {name} extends Component {{\n  render() {{\n    return (\n      <div className="{name.lower()}">\n        <h2>{name}</h2>\n      </div>\n    );\n  }}\n}}\n',
            },
            "vue": {
                "functional": f'<template>\n  <div class="{name.lower()}">\n    <h2>{name}</h2>\n  </div>\n</template>\n\n<script>\nexport default {{\n  name: "{name}",\n}};\n</script>\n\n<style scoped>\n.{name.lower()} {{\n  padding: 20px;\n}}\n</style>\n',
            },
        }

        templates = component_templates.get(framework, {})
        content = templates.get(template_type)
        if not content:
            return {"success": False, "error": f"Template tidak tersedia untuk {framework}/{template_type}"}

        ext_map = {"react": ".jsx", "vue": ".vue", "nextjs": ".jsx"}
        ext = ext_map.get(framework, ".js")
        comp_dir = "src/components" if framework in ("react", "vue") else "components"
        file_path = os.path.join(comp_dir, f"{name}{ext}")

        return self.write_file(project_dir, file_path, content)

    def add_api_route(self, project_dir: str, route_path: str, method: str = "GET",
                      handler_code: str = "", framework: str = "express") -> dict:
        route_templates = {
            "express": f'\napp.{method.lower()}("{route_path}", (req, res) => {{\n  {handler_code or "res.json({ message: \"ok\" })"}\n}});\n',
            "flask": f'\n@app.route("{route_path}", methods=["{method.upper()}"])\ndef {route_path.replace("/", "_").strip("_")}():\n    {handler_code or "return jsonify({\"message\": \"ok\"})"}\n',
            "fastapi": f'\n@app.{method.lower()}("{route_path}")\nasync def {route_path.replace("/", "_").strip("_")}():\n    {handler_code or "return {\"message\": \"ok\"}"}\n',
        }

        route_code = route_templates.get(framework)
        if not route_code:
            return {"success": False, "error": f"Framework '{framework}' tidak didukung untuk route"}

        entry_files = {
            "express": "server.js",
            "flask": "app.py",
            "fastapi": "main.py",
        }
        entry_file = entry_files.get(framework, "server.js")
        full_path = os.path.join(project_dir, entry_file)

        if not os.path.exists(full_path):
            return {"success": False, "error": f"Entry file tidak ditemukan: {entry_file}"}

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            if framework == "express":
                insert_before = "app.listen("
                if insert_before in content:
                    content = content.replace(insert_before, route_code + "\n" + insert_before, 1)
                else:
                    content += route_code
            else:
                content += route_code

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {"success": True, "route": route_path, "method": method, "file": entry_file}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @property
    def output_dir(self):
        return getattr(self, "_output_dir", "data/webdev_exports")

    @output_dir.setter
    def output_dir(self, value):
        self._output_dir = value
        os.makedirs(value, exist_ok=True)
