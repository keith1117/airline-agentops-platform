(() => {
  const picker = document.querySelector('.timezone-picker');
  const form = document.getElementById('timezone-form');
  if (!picker || !form) return;
  async function apply(zone, manual) {
    const body = new FormData(form);
    body.set('timezone', zone);
    body.set('manual', manual ? '1' : '0');
    try {
      const response = await fetch(form.action, {method: 'POST', body});
      if (!response.ok) {
        document.getElementById('timezone-error').textContent = 'Enter a valid IANA timezone.';
        return;
      }
      document.getElementById('timezone-label').textContent = zone;
      picker.dataset.timezone = zone;
      picker.dataset.manual = manual ? '1' : '0';
      form.elements.timezone.value = zone;
      const formatter = new Intl.DateTimeFormat('en-GB', {
        timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short'
      });
      document.querySelectorAll('time[data-user-time]').forEach(node => {
        node.textContent = formatter.format(new Date(node.dateTime)) + ' (' + zone + ')';
      });
      document.getElementById('timezone-error').textContent = '';
    } catch (_) {
      document.getElementById('timezone-error').textContent = 'Timezone could not be saved. Try again.';
    }
  }
  form.addEventListener('submit', event => {
    event.preventDefault();
    apply(form.elements.timezone.value, true);
  });
  const detected = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  document.getElementById('timezone-auto').addEventListener('click', () => apply(detected, false));
  if (picker.dataset.manual !== '1' && detected !== picker.dataset.timezone) apply(detected, false);
})();
