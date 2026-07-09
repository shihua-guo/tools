(function () {
  const textInput = document.querySelector('textarea[name="title"]');
  const sizeInput = document.querySelector('input[name="title_size_percent"]');
  const colorInput = document.querySelector('input[name="text_color"]');
  const fontInput = document.querySelector('input[name="font_file"]');
  const editors = document.querySelectorAll("[data-editor]");
  let customFontFamily = "";

  if (!textInput || !sizeInput || !colorInput || editors.length === 0) {
    return;
  }

  const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);

  function syncTextLayers() {
    const text = textInput.value.trim() || "封面文字";
    const sizePercent = Number(sizeInput.value || 8);
    const color = colorInput.value || "#ffffff";

    editors.forEach((editor) => {
      const stage = editor.querySelector("[data-preview-kind]");
      const layer = editor.querySelector("[data-text-layer]");
      if (!stage || !layer) {
        return;
      }

      layer.textContent = text;
      layer.style.color = color;
      layer.style.fontSize = `${Math.max(18, stage.clientWidth * sizePercent / 100)}px`;
      layer.style.fontFamily = customFontFamily || "";
      keepLayerInsideStage(editor);
    });
  }

  async function loadPreviewFont() {
    const file = fontInput && fontInput.files && fontInput.files[0];
    if (!file) {
      customFontFamily = "";
      syncTextLayers();
      return;
    }

    const family = `cover-font-${Date.now()}`;
    const url = URL.createObjectURL(file);
    try {
      const face = new FontFace(family, `url("${url}")`);
      await face.load();
      document.fonts.add(face);
      customFontFamily = `"${family}"`;
    } catch (error) {
      customFontFamily = "";
    } finally {
      syncTextLayers();
    }
  }

  function setPreviewUrl(image, url) {
    if (image.dataset.objectUrl) {
      URL.revokeObjectURL(image.dataset.objectUrl);
    }
    image.dataset.objectUrl = url;
    image.src = url;
  }

  async function previewUrlForFile(file) {
    const formData = new FormData();
    formData.append("image", file);

    const response = await fetch("/preview-image", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return URL.createObjectURL(await response.blob());
  }

  function setLayerPosition(editor, xPercent, yPercent) {
    const layer = editor.querySelector("[data-text-layer]");
    const xInput = editor.querySelector('input[name$="_text_x"]');
    const yInput = editor.querySelector('input[name$="_text_y"]');
    if (!layer || !xInput || !yInput) {
      return;
    }

    layer.style.left = `${xPercent}%`;
    layer.style.top = `${yPercent}%`;
    xInput.value = xPercent.toFixed(2);
    yInput.value = yPercent.toFixed(2);
  }

  function keepLayerInsideStage(editor) {
    const stage = editor.querySelector("[data-preview-kind]");
    const layer = editor.querySelector("[data-text-layer]");
    const xInput = editor.querySelector('input[name$="_text_x"]');
    const yInput = editor.querySelector('input[name$="_text_y"]');
    if (!stage || !layer || !xInput || !yInput || stage.clientWidth === 0 || stage.clientHeight === 0) {
      return;
    }

    const maxX = Math.max(0, 100 - layer.offsetWidth / stage.clientWidth * 100);
    const maxY = Math.max(0, 100 - layer.offsetHeight / stage.clientHeight * 100);
    const xPercent = clamp(Number(xInput.value || 0), 0, maxX);
    const yPercent = clamp(Number(yInput.value || 0), 0, maxY);
    setLayerPosition(editor, xPercent, yPercent);
  }

  function bindPreview(editor) {
    const kind = editor.dataset.editor;
    const fileInput = editor.querySelector(`input[name="${kind}_image"]`);
    const stage = editor.querySelector(`[data-preview-kind="${kind}"]`);
    const image = editor.querySelector("[data-preview-image]");
    const layer = editor.querySelector("[data-text-layer]");
    const xInput = editor.querySelector(`input[name="${kind}_text_x"]`);
    const yInput = editor.querySelector(`input[name="${kind}_text_y"]`);

    if (!fileInput || !stage || !image || !layer || !xInput || !yInput) {
      return;
    }

    setLayerPosition(editor, Number(xInput.value || 8), Number(yInput.value || 60));

    fileInput.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        stage.classList.remove("has-image");
        image.removeAttribute("src");
        return;
      }

      image.onload = () => {
        stage.classList.add("has-image");
        syncTextLayers();
      };
      image.onerror = () => {
        stage.classList.remove("has-image");
      };

      try {
        setPreviewUrl(image, await previewUrlForFile(file));
      } catch (error) {
        setPreviewUrl(image, URL.createObjectURL(file));
      }
    });

    layer.addEventListener("pointerdown", (event) => {
      if (!stage.classList.contains("has-image")) {
        return;
      }

      event.preventDefault();
      layer.setPointerCapture(event.pointerId);

      const stageBox = stage.getBoundingClientRect();
      const layerBox = layer.getBoundingClientRect();
      const offsetX = event.clientX - layerBox.left;
      const offsetY = event.clientY - layerBox.top;

      const move = (moveEvent) => {
        const maxLeft = Math.max(0, stageBox.width - layer.offsetWidth);
        const maxTop = Math.max(0, stageBox.height - layer.offsetHeight);
        const left = clamp(moveEvent.clientX - stageBox.left - offsetX, 0, maxLeft);
        const top = clamp(moveEvent.clientY - stageBox.top - offsetY, 0, maxTop);
        setLayerPosition(editor, left / stageBox.width * 100, top / stageBox.height * 100);
      };

      const stop = () => {
        layer.removeEventListener("pointermove", move);
        layer.removeEventListener("pointerup", stop);
        layer.removeEventListener("pointercancel", stop);
      };

      layer.addEventListener("pointermove", move);
      layer.addEventListener("pointerup", stop);
      layer.addEventListener("pointercancel", stop);
    });
  }

  editors.forEach(bindPreview);
  textInput.addEventListener("input", syncTextLayers);
  sizeInput.addEventListener("input", syncTextLayers);
  colorInput.addEventListener("input", syncTextLayers);
  if (fontInput) {
    fontInput.addEventListener("change", loadPreviewFont);
  }
  window.addEventListener("resize", syncTextLayers);
  syncTextLayers();
})();
