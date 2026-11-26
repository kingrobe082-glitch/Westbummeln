// Rückfrage vor Moderationsaktionen: <form data-confirm="Frage?">. Ohne Inline-Skript wegen der CSP.
document.addEventListener('submit', event => {
  const question = event.target.dataset && event.target.dataset.confirm;
  if (question && !window.confirm(question)) event.preventDefault();
});
