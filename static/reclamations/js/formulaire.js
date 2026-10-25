(function () {
  const description = document.getElementById("id_description");
  const counter = document.getElementById("description-count");
  if (!description || !counter) return;
  const update = () => { counter.textContent = `${description.value.trim().length}/20 caractères minimum`; };
  description.addEventListener("input", update);
  update();
})();
