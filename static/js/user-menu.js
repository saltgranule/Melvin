// closes the navbar account menu on a click outside it or on escape. it's a <details>, so it opens without this
(function () {
    var menu = document.querySelector(".user-menu");
    if (!menu) return;

    document.addEventListener("click", function (event) {
        if (menu.open && !menu.contains(event.target)) menu.open = false;
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && menu.open) {
            menu.open = false;
            menu.querySelector("summary").focus();
        }
    });
})();
