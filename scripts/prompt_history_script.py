import math
import os
import re
import time
import uuid
import html

from PIL import Image
import gradio as gr
import modules.images as images
# Forge Neo: modules.generation_parameters_copypaste was renamed to modules.infotext_utils
try:
    import modules.infotext_utils as parameters_copypaste
except ImportError:  # fallback for classic A1111
    import modules.generation_parameters_copypaste as parameters_copypaste
from modules import script_callbacks, shared, scripts
from lib_history import global_state, history, hijacker, image_process_hijacker

config_dir = os.path.join(scripts.basedir(), "data")
config_file_path = "data.json"
current_code = ""
origin_code = "'"
active_id = ""
manual_save_history = None
# pagination
total_pages = 1
current_page = 1

# transient witness that the last entry was really stored (manual save).
# Set by manually_save() and returned straight to the "Save" button's output
# (gr.HTML) — the browser watches that element and fires a floating toast.
save_confirmation = ""


def read_config():
    # ensure history exist
    os.makedirs(config_dir, exist_ok=True)
    cfgPath = os.path.join(config_dir, config_file_path)
    # only load config data if exist
    if os.path.exists(cfgPath):
        with open(cfgPath, "r", encoding="utf-8") as f:
            import json
            data = json.load(f)
            for hr in data:
                h = history.History(hr["id"], hr.get("name"), hr.get("model"),
                                    prompt=hr.get("prompt", hr.get("info_text", "")),
                                    params=hr.get("params", ""))
                h.created_at = hr.get("created_at", time.time())
                global_state.config_histories.append(h)

def to_json():
    import json
    if not global_state.config_histories:
        return ""
    data = list()
    for h in global_state.config_histories:
        data.append(h.to_json())
    return json.dumps(data, indent=2)

def save_history():
    cfgPath = os.path.join(config_dir, config_file_path)
    with open(cfgPath, "w", encoding="utf-8") as outfile:
        outfile.write(to_json())

def add_config(id: str, name: str, model: str, info_text: str, img):
    # init new history - the prompt is always stored; the full generation info
    # (parameters) is only kept when the "Also save generation parameters" option is on
    full_info = (info_text or "").rstrip("\n")
    h = history.History(id, name, model, prompt=full_info,
                        params=full_info if global_state.save_params else "")

    # in case of not automatic save, we must store few items in case of manual saved
    if not global_state.automatic_save:
        global manual_save_history
        manual_save_history = {
            "history": h,
            "image": img,
        }
        return

    # save image
    _save_image(img, id)

    # add history to list
    global_state.config_histories.insert(0, h)

    # save to file
    save_history()

    # reload the UI
    global_state.config_changed = True
    return h

def _save_image(img, id: str):
    imageType = global_state.save_thumbnail
    if imageType in ("", None): imageType = "full"
    if imageType == "thumbnail":
        new_width  = 300
        new_height = int(new_width * img.height / img.width)
        img = img.resize((new_width, new_height), Image.LANCZOS)
    images.save_image(image=img, path=global_state.history_path, basename="", forced_filename=f"{id}", extension="jpg", save_to_dirs=False)

def manually_save():
    global manual_save_history, save_confirmation
    # reset so a failed/absent save clears the witness (element shows nothing)
    save_confirmation = ""
    if manual_save_history is not None:
        img = manual_save_history["image"]
        h = manual_save_history["history"]
        # save image
        _save_image(img, h.id)

        # add history to list
        global_state.config_histories.insert(0, h)

        # save to file
        save_history()

        # reload the UI
        global_state.config_changed = True

        # visual witness that the entry was really stored: returned to the
        # "Save" button's output (a gr.HTML that only changes here). The total
        # count is included so the string is unique per save (the browser only
        # fires the toast on a text change) and it doubles as "how many now".
        save_confirmation = "✓ Saved " + time.strftime("%H:%M:%S") + \
                            " (" + str(len(global_state.config_histories)) + " total)"

        # clean
        manual_save_history = None
    # absent/failed save: "" is returned -> nothing shown
    return save_confirmation

def export_txt():
    # Build the export content. Returns a file path; the gr.File output
    # component (wired in on_ui_tabs) postprocesses it into a downloadable
    # FileData. Must NOT return a gr.File instance or a DownloadButton value:
    # the old code passed a label string to DownloadButton(value=...), so the
    # browser fetched "/file=<label>" (a 403) and opened a blank tab, and the
    # gr.File(path, file_name=...) return would have raised because Gradio's
    # File component has no file_name argument.
    if not global_state.config_histories:
        raise gr.Error("No prompts to export.")
    lines = []
    for h in global_state.config_histories:
        lines.append(f"--- {time.ctime(h.created_at)} ---")
        lines.append(h.prompt)
        if h.params:
            lines.append(h.params)
        lines.append("")
    content = "\n".join(lines).strip() + "\n"
    path = os.path.join(config_dir, "prompts_export.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    # gr.update: fill the gr.File output with the file AND reveal it. A plain
    # path would populate the value but the component starts hidden. Verified
    # in Gradio 4.40 that this yields a FileData (orig_name=prompts_export.txt)
    # with a served /file= url, which the browser turns into a real download.
    return gr.update(value=path, visible=True)

def before_ui():
    global config_dir
    global_state.is_enabled = shared.opts.data.get('prompt_history_enabled', True)
    global_state.automatic_save = shared.opts.data.get('prompt_history_automatic_save_info', True)
    global_state.save_thumbnail = shared.opts.data.get('prompt_history_save_thumbnail', "full")
    global_state.table_thumb_size = int(shared.opts.data.get('prompt_history_preview_thumb_size_inline', 96))
    global_state.items_per_page = int(shared.opts.data.get('prompt_history_items_per_page', 15))
    global_state.save_params = shared.opts.data.get('prompt_history_save_params', False)
    global_state.hover_tooltip = shared.opts.data.get('prompt_history_hover_tooltip', True)
    setup_data_dir = shared.opts.data.get('prompt_history_data_path', config_dir)
    if setup_data_dir != "":
        config_dir = setup_data_dir
        global_state.history_path = setup_data_dir
    else:
        global_state.history_path = config_dir
    global_state.add_config = add_config
    read_config()

def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as ui:
        with gr.Row():
            save_last_prompt_btn = gr.Button("Save Last Generated Info", elem_id="prompt_history_save_btn", visible=not global_state.automatic_save)
            # witness that an entry was really stored ("✓ Saved HH:MM:SS (N total)");
            # sits right next to the Save button. Filled only by that button's
            # handler; a floating toast (see javascript/) mirrors it so the
            # confirmation is visible even from the txt2img tab.
            save_status = gr.HTML("", elem_id="prompt_history_save_status")
            # A plain trigger button: it must NOT be a DownloadButton with a
            # string value, because Gradio treats that string as a file path and
            # the browser ends up fetching "/file=<label>" (a 403 / blank tab).
            # The actual file is produced by export_txt() and shown in the
            # gr.File output below, which Gradio serves as a real download.
            export_btn = gr.Button("📄 Export prompts (.txt)", elem_id="prompt_history_export_btn")
        with gr.Row():
            # Output of the export: hidden until the user clicks Export, then it
            # fills with the generated .txt and the browser gets a download link.
            export_file = gr.File(
                label="Exported prompts (.txt)",
                visible=False,
                interactive=False,
                elem_id="prompt_history_export_file",
            )
        with gr.Row():
            with gr.Column(scale=7):
                # list display column
                table = gr.HTML('Loading...')
                # show_progress="hidden": the 1 Hz poll must not show the Gradio
                # pending/generating overlay on the table (it made it flicker)
                ui.load(fn=history_table, inputs=[], outputs=[table, save_last_prompt_btn], every=1, show_progress="hidden")
                # receiver buttons
                item_id_text = gr.Text(elem_id="prompt_history_item_id_text", visible=False)
                click_item_btn = gr.Button(elem_id="prompt_history_click_item_btn", visible=False)
                delete_item_btn = gr.Button(elem_id="prompt_history_delete_item_btn", visible=False)
                prev_btn = gr.Button(elem_id="prompt_history_prev_btn", visible=False)
                next_btn = gr.Button(elem_id="prompt_history_next_btn", visible=False)
                select_page_text = gr.Text(elem_id="prompt_history_select_page_text", visible=False)
                select_page_btn = gr.Button(elem_id="prompt_history_select_page_btn", visible=False)
            with gr.Column(scale=3): # image preview and details column
                with gr.Row():
                    # image preview
                    preview_image = gr.Image(
                        label="Preview",
                        show_label=True,
                        interactive=False,
                        width=300,
                    )
                with gr.Row():
                    apply_btn = gr.Button("Apply")
                with gr.Row():
                    edit_btn =  gr.Button("🖊️", visible=False, elem_classes=["tool_fixed"])
                    revert_btn =  gr.Button("❌", visible=False, elem_classes=["tool_fixed"])
                    save_btn = gr.Button("💾", visible=False, elem_classes=["tool_fixed"])
                with gr.Row():
                    prompt_code = gr.Code(
                        label="Prompt",
                        show_label=True,
                        interactive=False,
                    )
                with gr.Row():
                    code_block = gr.Code(
                            label="Parameters (Apply source)",
                            show_label=True,
                            interactive=False,
                            visible=False,
                        )
        # manual save last generated info (the return value fills the witness
        # element; an absent buffer returns "" so nothing is shown)
        save_last_prompt_btn.click(
            fn=manually_save,
            outputs=[save_status],
        )
        # export all prompts to a .txt file
        export_btn.click(
            fn=export_txt,
            outputs=[export_file],
        )

        # process when click edit button
        edit_btn.click(
            fn=lambda: {
                code_block: gr.update(interactive=True),
                revert_btn: gr.update(visible=True),
                save_btn: gr.update(visible=True),
                edit_btn: gr.update(visible=False),
            },
            outputs=[code_block, revert_btn, save_btn, edit_btn]
        )

        def prev_func():
            global current_page
            if global_state.config_changed: return
            global_state.config_changed = True
            current_page -= 1
            if current_page <= 0: current_page = 1
        prev_btn.click(
            fn=prev_func,
        )

        def select_page_func(page: str):
            total_items = len(global_state.config_histories)
            total_pages = math.floor(total_items / global_state.items_per_page)
            if total_pages * global_state.items_per_page < total_items:
                total_pages += 1
            input_page = int(page, 10)
            if input_page > 0 & input_page <= total_pages:
                global current_page
                if global_state.config_changed: return
                global_state.config_changed = True
                current_page = input_page
        select_page_btn.click(
            fn=select_page_func,
            inputs=[select_page_text],
        )

        def next_func():
            global current_page
            if global_state.config_changed: return
            global_state.config_changed = True
            current_page += 1
            if current_page > total_pages: current_page = total_pages
        next_btn.click(
            fn=next_func,
        )

        # revert code func
        def revert_func():
            global current_code
            current_code = origin_code
            return {
                code_block: gr.update(value=origin_code, interactive=False),
                revert_btn: gr.update(visible=False),
                save_btn: gr.update(visible=False),
                edit_btn: gr.update(visible=True),
            }
        revert_btn.click(
            fn=revert_func,
            outputs=[code_block, revert_btn, save_btn, edit_btn]
        )

        # save code func
        def code_change_func(text: str):
            global current_code
            current_code = text
        code_block.change(
            fn=code_change_func,
            inputs=[code_block],
            outputs=[]
        )
        def apply_func():
            # edit info code in history object and save to file
            global active_id, current_code
            for h in global_state.config_histories:
                if h.id == active_id:
                    if h.params or global_state.save_params:
                        # parameters mode: edited text is the full generation info
                        h.params = current_code
                        h.prompt = current_code.splitlines(True)[0].rstrip("\n").strip()
                    else:
                        h.prompt = current_code
                    h.name = h.prompt[:64]
                    save_history()
                    break
            # update state
            return {
                code_block: gr.update(interactive=False),
                revert_btn: gr.update(visible=False),
                save_btn: gr.update(visible=False),
                edit_btn: gr.update(visible=True),
            }
        save_btn.click(
            fn=apply_func,
            outputs=[code_block, revert_btn, save_btn, edit_btn]
        )

        # register paste for apply button (uses the hidden full-info field)
        parameters_copypaste.register_paste_params_button(parameters_copypaste.ParamBinding(
            paste_button=apply_btn, tabname="txt2img", source_text_component=code_block, source_image_component=None,
        ))

        # process when click to item
        click_item_btn.click(
            fn=on_click_item,
            inputs=[item_id_text],
            outputs=[preview_image, prompt_code, code_block, code_block, edit_btn],
            show_progress=False,
        )

        # process when delete button
        delete_item_btn.click(
            fn=on_delete_item,
            inputs=[item_id_text],
            show_progress=False,
        )
        return [(ui, "Prompt History", "extension_prompt_history_tab")]

def on_delete_item(id: str):
    for _id in id.split(','):
        for h in global_state.config_histories:
            if h.id == _id:
                img_path = os.path.join(config_dir, f"{h.id}.jpg")
                if os.path.isfile(img_path):
                    os.remove(img_path)
                global_state.config_histories.remove(h)
    save_history()
    global_state.config_changed = True
    return []

def on_click_item(id: str):
    global current_code, origin_code, active_id
    for h in global_state.config_histories:
        if h.id == id:
            active_id = h.id
            # the "apply source" field: full generation info when parameters are
            # stored, the prompt otherwise
            apply_source = h.params if h.params else h.prompt
            current_code = apply_source
            origin_code = apply_source
            img_path = os.path.join(config_dir, f"{h.id}.jpg")
            global_state.config_changed = True
            img = Image.open(img_path) if os.path.isfile(img_path) else None
            return img, h.prompt, apply_source, gr.update(visible=bool(h.params) or global_state.save_params), gr.update(visible=True)

def config_changed(orginal_cfg:None, new_cfg:None):
    if orginal_cfg != new_cfg:
        global_state.config_changed = True
    return new_cfg

def history_table():
    global manual_save_history, total_pages, current_page, config_dir
    # update config variables
    global_state.is_enabled = config_changed(global_state.is_enabled, shared.opts.data.get('prompt_history_enabled', True))
    global_state.automatic_save = config_changed(global_state.automatic_save, shared.opts.data.get('prompt_history_automatic_save_info', True))
    global_state.save_thumbnail = config_changed(global_state.save_thumbnail, shared.opts.data.get('prompt_history_save_thumbnail', "full"))
    global_state.table_thumb_size = config_changed(global_state.table_thumb_size, int(shared.opts.data.get('prompt_history_preview_thumb_size_inline', 96)))
    global_state.items_per_page = config_changed(global_state.items_per_page, int(shared.opts.data.get('prompt_history_items_per_page', 15)))
    global_state.save_params = config_changed(global_state.save_params, shared.opts.data.get('prompt_history_save_params', False))
    global_state.hover_tooltip = config_changed(global_state.hover_tooltip, shared.opts.data.get('prompt_history_hover_tooltip', True))
    setup_data_dir = config_changed(config_dir, shared.opts.data.get('prompt_history_data_path', config_dir))
    if setup_data_dir != "" and setup_data_dir != config_dir:
        global_state.config_histories = list()
        config_dir = setup_data_dir
        global_state.history_path = setup_data_dir
        read_config()
    else:
        global_state.history_path = config_dir

    active_class = "pmt_item_active"

    if global_state.config_changed or not global_state.cached_data:

        code = f"""
        <div class="g-table-body">
        <button class="lg secondary gradio-button" onclick="return promptHistoryMultiselectDelete()"  style="padding: 0 10px;" id="prompt_history_btn_delete_selected">❌ Delete Selected</button>
        <table cellspacing="0" class="g-table-list" id="prompt-history-table">
            <thead>
                <tr>
                    <th style="cursor: pointer;width: 80px;display: flex;flex-direction: row;">
                        <input type="checkbox"onclick="return promptHistorySelectAll(this)"  style="cursor:pointer;outline:1px solid #dadada;" />
                    </th>
                    <th class="g-table-list-col-title g-table-list-col-sku required ">Prompt</th>
                    <th class="g-table-list-col-title g-table-list-col-sku required ">Preview</th>
                    <th class="g-table-list-col-title g-table-list-col-listing opt g-table-list-rwd">Created At</th>
                    <th class="g-table-list-col-title g-table-list-col-date required">Actions</th>
                </tr>
            </thead>
            <tbody>
        """

        # calculate pagination
        total_items = len(global_state.config_histories)
        total_pages = math.floor(total_items / global_state.items_per_page)
        if total_pages * global_state.items_per_page < total_items:
            total_pages += 1
        if current_page <= 0: current_page = 1
        if current_page > total_pages: current_page = total_pages
        start_idx = (current_page - 1) * global_state.items_per_page
        end_idx = start_idx + global_state.items_per_page
        if end_idx > total_items: end_idx = total_items

        # render page
        for h in global_state.config_histories[start_idx:end_idx]:
            item_class = ""
            if h.id == active_id:
                item_class = active_class
            # hover tooltip (custom JS + native title) only when the option is enabled
            if global_state.hover_tooltip:
                tooltip_class = " pmt-prompt-cell"
                title_attr = ' title="' + html.escape(h.prompt, quote=True).replace("\n", " ") + '"'
            else:
                tooltip_class = ""
                title_attr = ""
            on_click_view_item_fn =  '"' + html.escape(f"""return promptHistoryItemClick('{h.id}')""") + '"'
            on_click_delete_item_fn =  '"' + html.escape(f"""return promptHistoryItemDelete('{h.id}')""") + '"'
            code += f"""<tr class="{item_class}">
                        <td style="cursor: pointer;vertical-align:top;" onclick="return promptHistorySelect(this)">
                            <input type="checkbox" value="{h.id}" style="pointer-events: none;cursor:pointer;outline:1px solid #dadada;" />
                        </td>
                        <td class="{tooltip_class.strip()}" style="cursor: pointer;overflow: hidden;text-overflow: ellipsis;white-space: nowrap;max-width: 420px;"{title_attr} onclick={on_click_view_item_fn}>{html.escape(h.prompt)}</td>
                        <td style="cursor: pointer;vertical-align:top;" onclick={on_click_view_item_fn}>
                            <img src="/file={config_dir}{os.sep}{h.id}.jpg" style="max-width:{global_state.table_thumb_size}px;max-height:{global_state.table_thumb_size}px;">
                        </td>
                        <td style="cursor: pointer;" onclick={on_click_view_item_fn}>{time.ctime(h.created_at)}</td>
                        <td style="width: 110px;"><a onclick={on_click_delete_item_fn} class="g-actions-button g-actions-button-pager">🗑️ Delete</a></td>
                    </tr>"""

        code += f"""
            </tbody>
        </table>
        <div class="g-table-list-pagination">
            <div class="g-table-list-pagination-col">
                <a href="#" class="g-actions-button g-actions-button-pager" onclick="return promptHistoryPrev()">◀️</a>
        """
        if total_pages <= 6:
            for i in range(1, total_pages + 1):
                code += f"""<a href="#" class="g-actions-button g-actions-button-pager" onclick="return promptHistorySelectPage({i})">{i}</a>"""
        else:
            if current_page - 3 > 1:
                code += f"""<a href="#">...</a>"""
            for i in range(current_page - 3, current_page):
                if i > 0:
                    code += f"""<a href="#" class="g-actions-button g-actions-button-pager" onclick="return promptHistorySelectPage({i})">{i}</a>"""
            code += f"""<input id="page_input" value="{current_page}" data-testid="number-input" type="number" min="1" max="{total_pages}" step="1"  onchange="promptHistoryPageInputOnChange()">"""
            for i in range(current_page + 1, current_page + 4):
                if i <= total_pages:
                    code += f"""<a href="#" class="g-actions-button g-actions-button-pager" onclick="return promptHistorySelectPage({i})">{i}</a>"""
            if current_page < total_pages:
                code += f"""<a href="#">...</a>"""
        code += """
                <a href="#" class="g-actions-button g-actions-button-pager g-table-list-pager" onclick="return promptHistoryNext()">▶️</a>
            </div>
        </div>
        """
        global_state.cached_data = code
        global_state.config_changed = False
    return global_state.cached_data, gr.update(visible=(not global_state.automatic_save and manual_save_history is not None))

def on_ui_settings():
    section = ('prompt_history', 'Prompt History')
    shared.opts.add_option('prompt_history_enabled', shared.OptionInfo(True, 'Enabled', section=section))
    shared.opts.add_option('prompt_history_data_path', shared.OptionInfo(config_dir, 'Data Storage Path', section=section))
    shared.opts.add_option("prompt_history_preview_thumb_size_inline", shared.OptionInfo(96, "Preview thumbnail size in table", gr.Number, section=section))
    shared.opts.add_option("prompt_history_items_per_page", shared.OptionInfo(15, "Number of history items display per page", gr.Number, section=section))
    shared.opts.add_option('prompt_history_automatic_save_info', shared.OptionInfo(True, 'Automatic Save (If unset, prompts are saved only when you click "Save Last Generated Info")', section=section))
    shared.opts.add_option('prompt_history_save_params', shared.OptionInfo(False, 'Also save generation parameters (steps, sampler, seed... - prompt is always saved, parameters are optional)', section=section))
    shared.opts.add_option('prompt_history_hover_tooltip', shared.OptionInfo(True, 'Show full prompt on hover in the table', section=section))
    shared.opts.add_option('prompt_history_save_thumbnail', shared.OptionInfo(None, "Save Thumbnail", gr.Dropdown, lambda: {"choices": ["none", "thumbnail", "full"]}, section=section))


script_callbacks.on_ui_settings(on_ui_settings)
script_callbacks.on_before_ui(before_ui)
script_callbacks.on_ui_tabs(on_ui_tabs)
