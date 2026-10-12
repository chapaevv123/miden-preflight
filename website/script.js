const copy = document.querySelector('#copy');
copy?.addEventListener('click', async () => {
  await navigator.clipboard.writeText('cd demo/official-wallet-lock\n./run_demo.ps1');
  copy.textContent = 'Copied';
  window.setTimeout(() => { copy.textContent = 'Copy'; }, 1600);
});
