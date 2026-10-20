(function () {
    var form = document.getElementById("command-form");
    var content = document.getElementById("command-content");
    var counter = document.getElementById("command-count");
    var dirtyNote = document.getElementById("command-dirty");
    var preview = document.getElementById("command-preview");
    var effects = document.getElementById("command-effects");
    var sample = document.getElementById("command-sample");
    var refresh = document.getElementById("command-preview-refresh");

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null && text !== "") node.textContent = text;
        return node;
    }

    function renderCard(data) {
        var nodes = [];
        if (data.kind === "embed") {
            var embed = el("div", "command-embed");
            if (data.color) embed.style.borderLeftColor = data.color;
            if (data.title) embed.appendChild(el("div", "command-embed-title", data.title));
            if (data.url) embed.appendChild(el("div", "command-embed-link", data.url));
            if (data.description) embed.appendChild(el("div", "command-embed-description", data.description));
            (data.fields || []).forEach(function (field) {
                var item = el("div", "command-embed-field");
                item.appendChild(el("div", "command-embed-field-name", field.name || "\u200b"));
                item.appendChild(el("div", "command-embed-field-value", field.value || "\u200b"));
                embed.appendChild(item);
            });
            if (data.image) embed.appendChild(el("div", "command-embed-media", "Image: " + data.image));
            if (data.thumbnail) embed.appendChild(el("div", "command-embed-media", "Thumbnail: " + data.thumbnail));
            if (data.footer) embed.appendChild(el("div", "command-embed-footer", data.footer));
            nodes.push(embed);
        } else if (data.kind === "container") {
            var box = el("div", "command-container");
            if (data.color) box.style.borderLeftColor = data.color;
            (data.blocks || []).forEach(function (block) {
                if (block.type === "separator") {
                    box.appendChild(el("hr", "command-separator command-separator-" + block.size));
                } else {
                    box.appendChild(el("div", "command-container-text", block.text || "\u200b"));
                }
            });
            if ((data.buttons || []).length) {
                var row = el("div", "command-buttons");
                data.buttons.forEach(function (button) {
                    row.appendChild(el("span", "command-button", button.label || "Link"));
                });
                box.appendChild(row);
            }
            nodes.push(box);
        } else {
            nodes.push(el("div", "command-bubble", data.text || "Nothing to show."));
        }
        return nodes;
    }

    function showError(message) {
        preview.replaceChildren(el("p", "dashboard-field-error", message));
        effects.replaceChildren();
    }

    function showPreview(data) {
        preview.replaceChildren.apply(preview, renderCard(data));
        effects.replaceChildren();
        if ((data.effects || []).length) {
            effects.appendChild(el("p", "command-effects-heading", "Running it would:"));
            var list = el("ul", "command-effects-list");
            data.effects.forEach(function (text) {
                list.appendChild(el("li", null, text));
            });
            effects.appendChild(list);
            effects.appendChild(el("p", "dashboard-field-description",
                "Roles change only when the command is used."));
        }
    }

    var latest = 0;

    function updatePreview() {
        if (!form || !preview || !preview.getAttribute("data-url")) return;
        var ticket = ++latest;
        preview.classList.add("is-loading");
        var body = new FormData();
        body.append("csrf", form.elements.csrf.value);
        body.append("content", content.value);
        body.append("args", form.elements.args.value);
        body.append("sample", sample ? sample.value : "");

        fetch(preview.getAttribute("data-url"), {
            method: "POST",
            body: body,
            headers: { "X-Requested-With": "fetch" }
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (ticket !== latest) return;
                preview.classList.remove("is-loading");
                if (result.ok) {
                    showPreview(result.data);
                } else {
                    showError(result.data.error || "Couldn't make a preview.");
                }
            })
            .catch(function () {
                if (ticket !== latest) return;
                preview.classList.remove("is-loading");
                showError("Couldn't make a preview. Check your connection.");
            });
    }

    function updateCounter() {
        if (!counter || !content) return;
        counter.textContent = content.value.length + " / " + content.maxLength;
        counter.classList.toggle("is-near", content.value.length > content.maxLength * 0.9);
    }

    function insertSnippet(text, fromReference) {
        if (!content) return;
        var start = content.selectionStart;
        var end = content.selectionEnd;
        var before = content.value.slice(0, start);
        var startsBlock = text.charAt(0) === "{";
        var prefix = startsBlock && before.length && before.charAt(before.length - 1) !== "\n" ? "\n" : "";
        content.value = before + prefix + text + content.value.slice(end);
        var caret = before.length + prefix.length + text.length;
        content.focus({ preventScroll: !!fromReference });
        content.setSelectionRange(caret, caret);
        if (fromReference) content.scrollIntoView({ block: "center", behavior: "smooth" });
        content.dispatchEvent(new Event("input", { bubbles: true }));
    }

    document.querySelectorAll("[data-insert]").forEach(function (button) {
        button.addEventListener("click", function () {
            insertSnippet(
                button.getAttribute("data-insert").replace(/&#10;/g, "\n"),
                button.classList.contains("command-ref-insert")
            );
        });
    });

    var saved = form ? new URLSearchParams(new FormData(form)).toString() : "";
    var submitting = false;

    function isDirty() {
        return form && new URLSearchParams(new FormData(form)).toString() !== saved;
    }

    function syncDirty() {
        if (dirtyNote) dirtyNote.hidden = !isDirty();
    }

    if (form) {
        form.addEventListener("input", syncDirty);
        form.addEventListener("change", syncDirty);
        form.addEventListener("submit", function (event) {
            if (submitting) {
                event.preventDefault();
                return;
            }
            submitting = true;
            var submit = form.querySelector("button[type=submit]");
            if (submit) {
                submit.setAttribute("data-label", submit.textContent);
                submit.disabled = true;
                submit.textContent = "Saving...";
            }
        });
        window.addEventListener("beforeunload", function (event) {
            if (!submitting && isDirty()) {
                event.preventDefault();
                event.returnValue = "";
            }
        });
        document.addEventListener("keydown", function (event) {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
                event.preventDefault();
                form.requestSubmit();
            }
        });
    }

    var filter = document.getElementById("reference-filter");
    var emptyNote = document.getElementById("reference-empty");

    function applyFilter() {
        var query = filter.value.trim().toLowerCase();
        var words = query.split(/\s+/).filter(Boolean);
        var anyVisible = false;

        document.querySelectorAll("[data-ref-item]").forEach(function (item) {
            var text = (item.getAttribute("data-search") || "").toLowerCase();
            var match = words.every(function (word) { return text.indexOf(word) !== -1; });
            item.hidden = !match;
        });
        document.querySelectorAll("[data-ref-group], [data-ref-section]").forEach(function (group) {
            var visible = group.querySelector("[data-ref-item]:not([hidden])");
            group.hidden = !visible && words.length > 0;
            if (words.length && visible) group.open = true;
            if (visible) anyVisible = true;
        });
        if (emptyNote) emptyNote.hidden = anyVisible || words.length === 0;
    }

    if (filter) {
        filter.addEventListener("input", applyFilter);
    }

    var menus = document.querySelectorAll(".command-menu");

    function closeMenusExcept(keep) {
        menus.forEach(function (menu) {
            if (menu !== keep) menu.open = false;
        });
    }

    menus.forEach(function (menu) {
        menu.addEventListener("toggle", function () {
            if (menu.open) closeMenusExcept(menu);
        });
        var close = menu.querySelector("[data-menu-close]");
        if (close) {
            close.addEventListener("click", function () { menu.open = false; });
        }
    });

    document.addEventListener("click", function (event) {
        menus.forEach(function (menu) {
            if (!menu.open) return;
            var toggle = menu.querySelector(".command-menu-toggle");
            var panel = menu.querySelector(".command-menu-panel");
            if (toggle.contains(event.target) || panel.contains(event.target)) return;
            menu.open = false;
        });
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeMenusExcept(null);
    });

    var dialog = document.getElementById("command-dialog");
    var dialogForm = document.getElementById("command-dialog-form");
    var dialogName = document.getElementById("command-dialog-name");
    var dialogTitle = document.getElementById("command-dialog-title");
    var dialogSubmit = document.getElementById("command-dialog-submit");
    var dialogCancel = document.getElementById("command-dialog-cancel");

    if (dialog && typeof dialog.showModal === "function") {
        document.querySelectorAll("[data-prompt]").forEach(function (button) {
            button.addEventListener("click", function () {
                var menu = button.closest(".command-menu");
                if (menu) menu.open = false;
                dialogForm.action = button.getAttribute("data-action");
                dialogTitle.textContent = button.getAttribute("data-title");
                dialogSubmit.textContent = button.getAttribute("data-label");
                dialogName.value = button.getAttribute("data-value").slice(0, 32);
                dialog.showModal();
                dialogName.select();
            });
        });
        dialogCancel.addEventListener("click", function () { dialog.close(); });
        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) dialog.close();
        });
        dialogForm.addEventListener("submit", function () {
            dialogSubmit.disabled = true;
        });
    }

    if (content) {
        content.addEventListener("input", function () {
            updateCounter();
            later();
        });
    }
    if (form && form.elements.args) form.elements.args.addEventListener("input", later);
    if (sample) sample.addEventListener("input", later);
    if (refresh) refresh.addEventListener("click", updatePreview);
    if (filter) filter.addEventListener("keydown", function (event) {
        if (event.key === "Escape") { filter.value = ""; applyFilter(); }
    });

    var timer = null;
    function later() {
        clearTimeout(timer);
        timer = setTimeout(updatePreview, 400);
    }

    document.querySelectorAll(".banner-success").forEach(function (banner) {
        setTimeout(function () {
            banner.classList.add("is-leaving");
            setTimeout(function () { banner.hidden = true; }, 300);
        }, 3000);
    });

    var address = new URL(window.location.href);
    if (address.searchParams.has("notice") || address.searchParams.has("problem")) {
        address.searchParams.delete("notice");
        address.searchParams.delete("problem");
        window.history.replaceState(null, "", address.pathname + address.search + address.hash);
    }

    updateCounter();
    syncDirty();
    if (form && preview && preview.getAttribute("data-url")) updatePreview();

    document.querySelectorAll("form[data-confirm]").forEach(function (confirmForm) {
        confirmForm.addEventListener("submit", function (event) {
            if (!window.confirm(confirmForm.getAttribute("data-confirm"))) {
                event.preventDefault();
                return;
            }
            submitting = true;
        });
    });

    window.addEventListener("pageshow", function (event) {
        if (!event.persisted || !form) return;
        submitting = false;
        var submit = form.querySelector("button[type=submit]");
        if (submit) {
            submit.disabled = false;
            submit.textContent = submit.getAttribute("data-label") || submit.textContent;
        }
    });
})();
