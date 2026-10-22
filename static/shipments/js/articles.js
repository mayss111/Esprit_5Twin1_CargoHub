(function () {
  const bouton = document.getElementById("ajouter-article");
  const liste = document.getElementById("articles");
  const total = document.getElementById("id_articles-TOTAL_FORMS");
  const modele = document.getElementById("article-vide");
  if (!bouton || !liste || !total || !modele) return;

  bouton.addEventListener("click", function () {
    const index = total.value;
    const html = modele.innerHTML.replaceAll("__prefix__", index);
    liste.insertAdjacentHTML("beforeend", html);
    total.value = String(Number(index) + 1);
  });
})();
