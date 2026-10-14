const form = document.querySelector("#convert-form");
const input = document.querySelector("#dwg-file");
const dropZone = document.querySelector("#drop-zone");
const dropTitle = document.querySelector("#drop-title");
const dropSubtitle = document.querySelector("#drop-subtitle");
const selected = document.querySelector("#selected-file");
const fileName = document.querySelector("#file-name");
const fileSize = document.querySelector("#file-size");
const clearButton = document.querySelector("#clear-file");
const convertButton = document.querySelector("#convert-button");
const message = document.querySelector("#message");
const serviceStatus = document.querySelector("#service-status");
const limit = document.querySelector("#limit");

let maxUploadMb = 100;
let serviceReady = false;
const configuredApiBaseUrl = (window.APP_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");
const isGithubPages = window.location.hostname.endsWith(".github.io");
const apiBaseUrl = configuredApiBaseUrl || (isGithubPages ? null : "");
const apiUrl = (path) => `${apiBaseUrl}${path}`;

function setMessage(text = "", kind = "") {
  message.textContent = text;
  message.className = `message ${kind}`.trim();
}

function showFile(file) {
  const validExtension = file?.name.toLowerCase().endsWith(".dwg");
  const validSize = file?.size <= maxUploadMb * 1024 * 1024;
  selected.hidden = !file;
  fileName.textContent = file?.name || "";
  fileSize.textContent = file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "";
  dropTitle.textContent = file ? "Arquivo selecionado" : "Arraste o arquivo aqui";
  dropSubtitle.textContent = file ? "clique para substituir" : "ou clique para procurar";
  convertButton.disabled = !(file && validExtension && validSize && serviceReady);

  if (file && !validExtension) setMessage("Selecione um arquivo .dwg.", "error");
  else if (file && !validSize) setMessage(`O limite e ${maxUploadMb} MB.`, "error");
  else setMessage();
}

input.addEventListener("change", () => showFile(input.files[0]));
clearButton.addEventListener("click", () => { input.value = ""; showFile(null); });

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});
dropZone.addEventListener("drop", (event) => {
  if (!event.dataTransfer.files.length) return;
  const transfer = new DataTransfer();
  transfer.items.add(event.dataTransfer.files[0]);
  input.files = transfer.files;
  showFile(input.files[0]);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = input.files[0];
  if (!file) return;

  convertButton.disabled = true;
  convertButton.classList.add("loading");
  convertButton.querySelector("span").textContent = "Convertendo";
  setMessage("A conversao pode levar alguns minutos.");

  try {
    const payload = new FormData();
    payload.append("file", file);
    const response = await fetch(apiUrl("/api/convert"), { method: "POST", body: payload });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Nao foi possivel converter o arquivo.");
    }

    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const matchedName = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i)?.[1];
    const outputName = matchedName ? decodeURIComponent(matchedName) : file.name.replace(/\.dwg$/i, ".glb");
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = outputName;
    anchor.click();
    URL.revokeObjectURL(url);
    setMessage("GLB criado. O download foi iniciado.", "success");
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    convertButton.disabled = false;
    convertButton.classList.remove("loading");
    convertButton.querySelector("span").textContent = "Converter para GLB";
  }
});

if (apiBaseUrl === null) {
  serviceStatus.textContent = "backend pendente";
  serviceStatus.className = "status offline";
  setMessage("O servico de conversao ainda nao foi conectado.");
} else {
  fetch(apiUrl("/api/health"))
    .then((response) => {
      if (!response.ok) throw new Error("Servico indisponivel");
      return response.json();
    })
    .then((health) => {
      maxUploadMb = health.maxUploadMb;
      limit.textContent = `${maxUploadMb} MB`;
      serviceReady = Boolean(health.converterConfigured);
      serviceStatus.textContent = serviceReady ? "configurado" : "sem credenciais";
      serviceStatus.className = `status ${serviceReady ? "ready" : "offline"}`;
      if (!serviceReady) setMessage("Configure as credenciais da Aspose no backend.");
      showFile(input.files[0]);
    })
    .catch(() => {
      serviceReady = false;
      serviceStatus.textContent = "indisponivel";
      serviceStatus.className = "status offline";
      setMessage("Nao foi possivel acessar o servico de conversao.", "error");
      showFile(input.files[0]);
    });
}

