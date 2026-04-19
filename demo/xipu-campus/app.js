const navToggle = document.getElementById("navToggle");
const siteNav = document.getElementById("siteNav");
const navLinks = Array.from(document.querySelectorAll(".site-nav a"));
const revealSections = document.querySelectorAll(".reveal-section");
const sections = Array.from(document.querySelectorAll("main section[id]"));

if (navToggle && siteNav) {
  navToggle.addEventListener("click", () => {
    const isOpen = siteNav.classList.toggle("is-open");
    navToggle.classList.toggle("is-open", isOpen);
    navToggle.setAttribute("aria-expanded", String(isOpen));
  });

  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      siteNav.classList.remove("is-open");
      navToggle.classList.remove("is-open");
      navToggle.setAttribute("aria-expanded", "false");
    });
  });
}

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  {
    threshold: 0.16,
    rootMargin: "0px 0px -8% 0px",
  }
);

revealSections.forEach((section) => {
  revealObserver.observe(section);
});

const navObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const currentId = entry.target.id;
      navLinks.forEach((link) => {
        link.classList.toggle(
          "is-active",
          link.dataset.section === currentId
        );
      });
    });
  },
  {
    threshold: 0.42,
    rootMargin: "-18% 0px -42% 0px",
  }
);

sections.forEach((section) => navObserver.observe(section));
