class ClassWatcher {
    constructor(targetNode, classToWatch, classAddedCallback, classRemovedCallback) {
        this.targetNode = targetNode
        this.classToWatch = classToWatch
        this.classAddedCallback = classAddedCallback
        this.classRemovedCallback = classRemovedCallback
        this.observer = null
        this.lastClassState = targetNode.classList.contains(this.classToWatch)

        this.init()
    }

    init() {
        this.observer = new MutationObserver(this.mutationCallback)
        this.observe()
    }

    observe() {
        this.observer.observe(this.targetNode, { attributes: true })
    }

    disconnect() {
        this.observer.disconnect()
    }

    mutationCallback = mutationsList => {
        for(let mutation of mutationsList) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                let currentClassState = mutation.target.classList.contains(this.classToWatch)
                if(this.lastClassState !== currentClassState) {
                    this.lastClassState = currentClassState
                    if(currentClassState) {
                        this.classAddedCallback()
                    }
                    else {
                        this.classRemovedCallback()
                    }
                }
            }
        }
    }
}

function promptHistorySelect(td) {
    let checkbox = td.querySelector("input[type=checkbox]")
    checkbox.checked = !checkbox.checked
    return false;
}


function promptHistorySelectAll(checkbox) {
    gradioApp().querySelectorAll("#prompt-history-table tbody input[type=checkbox]").forEach(p => p.checked = checkbox.checked)
}

function promptHistoryMultiselectDelete() {
    let checkboxes = gradioApp().querySelectorAll("#prompt-history-table tbody input:checked")
    if (checkboxes.length == 0) {
        return false;
    }

    checkboxes.forEach(p => {
        p.parentNode?.parentNode?.remove();
    })

    let textarea = gradioApp().querySelector('#prompt_history_item_id_text textarea');
    textarea.value = Array.from(checkboxes).map(p => p.value).join(',');
    updateInput(textarea);
    gradioApp().querySelector('#prompt_history_delete_item_btn').click();
}

function promptHistoryItemClick(id) {
    let textarea = gradioApp().querySelector('#prompt_history_item_id_text textarea');
    textarea.value = id;
    updateInput(textarea);

    gradioApp().querySelector('#prompt_history_click_item_btn').click();
}

function promptHistoryItemDelete(id) {
    let textarea = gradioApp().querySelector('#prompt_history_item_id_text textarea');
    textarea.value = id;
    updateInput(textarea);

    gradioApp().querySelector('#prompt_history_delete_item_btn').click();
}


function promptHistorySelectPage(page) {
    let textarea = gradioApp().querySelector('#prompt_history_select_page_text textarea');
    textarea.value = page;
    updateInput(textarea);

    gradioApp().querySelector('#prompt_history_select_page_btn').click();
}

function promptHistoryPageInputOnChange() {
  var x = gradioApp().querySelector('#page_input').value;
  promptHistorySelectPage(x)
}

function promptHistoryPrev() {
    gradioApp().querySelector('#prompt_history_prev_btn').click();
}

function promptHistoryNext() {
    gradioApp().querySelector('#prompt_history_next_btn').click();
}

function promptHistorySave() {
    gradioApp().querySelector('#prompt_history_save_btn').click();
}

function promptHistoryAutoRefresh() {
    // hijack ui
    const btn_c = gradioApp().querySelector('#txt2img_styles_edit_button')
    const pinit = gradioApp().querySelector('#txt2img_gallery_container');
    const pdiv = pinit.parentNode;
    if (pdiv !== undefined) {
        const btnSave = document.createElement("button");
        btnSave.id = "prompt_history_save_btn_txt2img"
        btnSave.onclick = function(){ return promptHistorySave();};
        btnSave.classList.add("lg", "secondary", "gradio-button", btn_c.classList[btn_c.classList.length-1])
        btnSave.innerHTML = "Save Last Generated Info"
        pdiv.insertBefore(btnSave, pinit);

        // watch btn
        const saveBtn = gradioApp().querySelector('#prompt_history_save_btn');
        let hideStateWatcher = new ClassWatcher(saveBtn, 'hide',
        ()=> {
            btnSave.classList.add("hide")
        },
        ()=>{
            btnSave.classList.remove("hide")
        });
    }

    const ll = setInterval(() => {
        const generating = gradioApp().querySelector('#tab_extension_prompt_history_tab .generating');
        if (generating !== undefined && generating !== null) {
            generating.remove();
            clearInterval(ll);
            return;
        }
    }, 1000);
}

// ---- hover tooltip: show the full prompt when the mouse hovers a table row ----
let pmtTooltip = null;
function promptHistoryTooltip() {
    if (!pmtTooltip) {
        pmtTooltip = document.createElement("div");
        pmtTooltip.id = "pmt-tooltip";
        pmtTooltip.style.display = "none";
        document.body.appendChild(pmtTooltip);
    }
    if (pmtTooltip.__installed) return;
    pmtTooltip.__installed = true;

    function moveTooltip(e) {
        const pad = 14;
        const rect = pmtTooltip.getBoundingClientRect();
        let x = e.clientX + pad;
        let y = e.clientY + pad;
        if (x + rect.width > window.innerWidth) x = e.clientX - rect.width - pad;
        if (y + rect.height > window.innerHeight) y = e.clientY - rect.height - pad;
        pmtTooltip.style.left = x + "px";
        pmtTooltip.style.top = y + "px";
    }

    document.addEventListener("mouseover", (e) => {
        const cell = e.target.closest && e.target.closest("#prompt-history-table .pmt-prompt-cell");
        if (!cell) return;
        const text = (cell.textContent || "").trim();
        if (!text) return;
        pmtTooltip.textContent = text;
        pmtTooltip.style.display = "block";
        moveTooltip(e);
    });
    document.addEventListener("mousemove", (e) => {
        if (pmtTooltip.style.display === "none") return;
        const cell = e.target.closest && e.target.closest("#prompt-history-table .pmt-prompt-cell");
        if (!cell) { pmtTooltip.style.display = "none"; return; }
        moveTooltip(e);
    });
    document.addEventListener("mouseout", (e) => {
        const cell = e.target.closest && e.target.closest("#prompt-history-table .pmt-prompt-cell");
        if (!cell) return;
        const to = e.relatedTarget && e.relatedTarget.closest
            ? e.relatedTarget.closest("#prompt-history-table .pmt-prompt-cell") : null;
        if (to !== cell) pmtTooltip.style.display = "none";
    });
}

// ---- floating "saved" toast: shown from ANY tab (you usually stay on txt2img) ----
let pmtToast = null;
let pmtToastTimer = null;
function promptHistoryShowToast(text) {
    if (!pmtToast) {
        pmtToast = document.createElement("div");
        pmtToast.id = "pmt-toast";
        document.body.appendChild(pmtToast);
    }
    pmtToast.textContent = text;
    pmtToast.classList.add("pmt-toast-show");
    if (pmtToastTimer) clearTimeout(pmtToastTimer);
    pmtToastTimer = setTimeout(() => {
        pmtToast.classList.remove("pmt-toast-show");
        pmtToastTimer = null;
    }, 5000);
}
function promptHistorySavedWitness() {
    // The "Save Last Generated Info" button's handler writes a confirmation
    // into this element (a gr.HTML that changes only on a successful save);
    // fire the toast on every NEW text (the server makes each one unique).
    const el = gradioApp().querySelector("#prompt_history_save_status");
    if (el && el.__witnessBound) return;
    if (el) {
        el.__witnessBound = true;
        let lastText = (el.textContent || "").trim();
        const mo = new MutationObserver(() => {
            const text = (el.textContent || "").trim();
            if (text && text !== lastText) {
                lastText = text;
                window.promptHistoryShowToast(text);
            }
        });
        mo.observe(el, { childList: true, characterData: true, subtree: true });
    }
}

onUiLoaded(async() => {
    promptHistoryAutoRefresh()
    promptHistoryTooltip()
    promptHistorySavedWitness()
});
