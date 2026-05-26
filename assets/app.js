
const search = document.querySelector('#search');
const cards = [...document.querySelectorAll('.episode-card')];
const buttons = [...document.querySelectorAll('[data-filter]')];
let active = 'all';
function apply(){
  const q = (search?.value || '').toLowerCase().trim();
  for (const card of cards){
    const show = card.dataset.show;
    const text = card.textContent.toLowerCase();
    const okFilter = active === 'all' || show === active;
    const okSearch = !q || text.includes(q);
    card.style.display = okFilter && okSearch ? '' : 'none';
  }
}
buttons.forEach(btn => btn.addEventListener('click', () => {
  active = btn.dataset.filter;
  buttons.forEach(b => b.classList.toggle('active', b === btn));
  apply();
}));
search?.addEventListener('input', apply);
