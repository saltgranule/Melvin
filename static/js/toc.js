// marks the section currently in view in "On this page", shared by the docs and legal pages
(function () {
    var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".docs-toc-link"));
    if (!tocLinks.length || !("IntersectionObserver" in window)) return;

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            tocLinks.forEach(function (link) {
                link.classList.toggle("is-current", link.hash === "#" + entry.target.id);
            });
        });
    }, { rootMargin: "0px 0px -70% 0px" });

    tocLinks.forEach(function (link) {
        var target = document.getElementById(decodeURIComponent(link.hash.slice(1)));
        if (target) observer.observe(target);
    });
})();
