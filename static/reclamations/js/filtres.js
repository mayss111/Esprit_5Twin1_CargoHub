(function () {
  document.querySelectorAll("form[data-auto-filter]").forEach((form) => {
    let timer;
    const submit = () => form.requestSubmit();
    form.querySelectorAll("select, input[type='date']").forEach((field) => field.addEventListener("change", submit));
    const search = form.querySelector("input[name='q']");
    if (search) {
      search.addEventListener("input", () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(submit, 350);
      });
    }
  });
})();
