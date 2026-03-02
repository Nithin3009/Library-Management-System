// Auto-dismiss flash messages after 4 seconds
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(el => {
    el.style.transition = 'opacity .5s, transform .5s';
    el.style.opacity = '0';
    el.style.transform = 'translateX(20px)';
    setTimeout(() => el.remove(), 500);
  });
}, 4000);

// Close sidebar on outside click (mobile)
document.addEventListener('click', e => {
  const sb = document.getElementById('sidebar');
  if (sb && sb.classList.contains('open') &&
      !sb.contains(e.target) &&
      !e.target.classList.contains('hamburger')) {
    sb.classList.remove('open');
  }
});
