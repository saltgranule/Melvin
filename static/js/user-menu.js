(function () {
    var menus = Array.prototype.slice.call(document.querySelectorAll(".user-menu, .nav-menu"));
    if (!menus.length) return;

    document.addEventListener("click", function (event) {
        menus.forEach(function (menu) {
            if (menu.open && !menu.contains(event.target)) menu.open = false;
        });
    });

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        menus.forEach(function (menu) {
            if (!menu.open) return;
            menu.open = false;
            menu.querySelector("summary").focus();
        });
    });
})();
