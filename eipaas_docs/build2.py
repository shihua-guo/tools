import json

with open('openapi.json', 'r', encoding='utf-8') as f:
    spec = json.load(f)

# Write to a JS file to bypass CORS when opening with file://
with open('openapi.js', 'w', encoding='utf-8') as f:
    f.write(f"window.API_SPEC = {json.dumps(spec)};\n")

html = """<!DOCTYPE html>
<html>
  <head>
    <title>EIPAAS Server API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- 使用 RapiDoc 引擎，与 EDICOM 官方文档一致 -->
    <script type="module" src="rapidoc-min.js"></script>
    <!-- 加载纯本地的数据变量 -->
    <script src="openapi.js"></script>
    <style>
      body { margin: 0; padding: 0; }
    </style>
  </head>
  <body>
    <rapi-doc 
      id="thedoc" 
      theme="light" 
      render-style="read" 
      show-header="false"
      allow-try="false"
      allow-server-selection="false"
    ></rapi-doc>
    <script>
      window.addEventListener('DOMContentLoaded', (event) => {
          let docEl = document.getElementById("thedoc");
          // 将加载好的 JSON 对象直接喂给 RapiDoc
          docEl.loadSpec(window.API_SPEC);
      });
    </script>
  </body>
</html>
"""

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("RapiDoc built successfully")
