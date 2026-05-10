import json

with open('openapi.json', 'r', encoding='utf-8') as f:
    spec = f.read()

html = f"""<!DOCTYPE html>
<html>
  <head>
    <title>EIPAAS Server API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body {{ margin: 0; padding: 0; }}
    </style>
  </head>
  <body>
    <div id="redoc-container"></div>
    <script>
      // 完整的 process 补丁
      var process = {{
        env: {{ NODE_ENV: 'production' }},
        nextTick: function(fn) {{ setTimeout(fn, 0); }}
      }};
      window.process = process;
    </script>
    <!-- 引用同目录下的本地 redoc.standalone.js 库，无需联网加载 -->
    <script src="redoc.standalone.js"></script>
    <script>
      // 直接将数据内嵌，避免 file:// 协议下的跨域(CORS)请求拦截
      const specObj = {spec};
      Redoc.init(specObj, {{}}, document.getElementById('redoc-container'));
    </script>
  </body>
</html>
"""

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("index.html successfully updated with embedded JSON")
