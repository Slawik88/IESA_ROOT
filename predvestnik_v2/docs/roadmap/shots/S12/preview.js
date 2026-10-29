'use strict';
const frames = [...document.querySelectorAll('iframe')];
function resetPreviews() {
  const width = document.getElementById('width').value;
  const exchange = document.getElementById('exchange').checked;
  const admin = document.getElementById('admin').checked;
  frames.forEach(frame => {
    const variant = frame.dataset.variant === 'a' && document.getElementById('six').checked ? 'a6' : frame.dataset.variant;
    frame.style.width = `${width}px`;
    frame.src = `phone.html?v=${variant}&w=${width}&exchange=${Number(exchange)}&admin=${Number(admin)}`;
  });
}
document.querySelectorAll('input,select').forEach(control => control.addEventListener('change', resetPreviews));
document.getElementById('reset').addEventListener('click', resetPreviews);
resetPreviews();
