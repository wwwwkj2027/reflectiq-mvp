/* ReflectIQ — Reflection Form Multi-Step Logic (4 steps) */

(function () {
  'use strict';

  const form = document.getElementById('reflectForm');
  if (!form) return;

  const panels = document.querySelectorAll('.form-panel');
  const steps = document.querySelectorAll('.step');
  const connectors = document.querySelectorAll('.step-connector');
  const TOTAL_STEPS = 4;

  let currentStep = 1;

  function showStep(n) {
    panels.forEach((p, i) => p.classList.toggle('active', i + 1 === n));
    steps.forEach((s, i) => {
      s.classList.remove('active', 'done');
      if (i + 1 === n) s.classList.add('active');
      if (i + 1 < n) s.classList.add('done');
    });
    connectors.forEach((c, i) => c.classList.toggle('done', i < n - 1));
    currentStep = n;
    removeAlert();
  }

  // Character counters
  document.querySelectorAll('textarea[data-maxlength]').forEach(function (ta) {
    const counter = ta.parentElement.querySelector('.char-count');
    if (!counter) return;
    function update() {
      const max = parseInt(ta.dataset.maxlength, 10);
      const len = ta.value.length;
      counter.textContent = len + ' / ' + max + ' characters';
      counter.style.color = len > max * 0.9 ? '#ef4444' : '';
    }
    ta.addEventListener('input', update);
    update();
  });

  // Step 1 → Step 2 (identification)
  const btnNext1 = document.getElementById('btnNext1');
  if (btnNext1) {
    btnNext1.addEventListener('click', function () {
      const name = document.getElementById('student_name').value.trim();
      const sid = document.getElementById('student_id').value.trim();
      if (!name) { showAlert('Please enter your full name.'); return; }
      if (!sid) { showAlert('Please enter your student ID.'); return; }
      showStep(2);
    });
  }

  // Step 2 → Step 3: AI follow-up
  const btnNext2 = document.getElementById('btnNext2');
  if (btnNext2) {
    btnNext2.addEventListener('click', async function () {
      const topic = document.getElementById('topic_id').value;
      const q1 = document.getElementById('q1').value.trim();
      if (q1.length < 20) { showAlert('Please share a bit more — at least a sentence or two.'); return; }

      btnNext2.disabled = true;
      showLoading(true);

      try {
        const resp = await fetch('/reflect/followup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic_id: topic, q1: q1 })
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
          showAlert(data.error || 'Something went wrong generating the follow-up. Please try again.');
          showLoading(false);
          btnNext2.disabled = false;
          return;
        }
        document.getElementById('followup_q_display').textContent = data.question;
        document.getElementById('followup_q').value = data.question;
        showLoading(false);
        showStep(3);
      } catch (e) {
        showAlert('Network error. Please try again.');
        showLoading(false);
        btnNext2.disabled = false;
      }
    });
  }

  // Step 3 → Step 4
  const btnNext3 = document.getElementById('btnNext3');
  if (btnNext3) {
    btnNext3.addEventListener('click', function () {
      const q2 = document.getElementById('q2').value.trim();
      if (q2.length < 20) { showAlert('Please write a bit more before continuing.'); return; }
      showStep(4);
    });
  }

  // Back buttons
  const btnBack2 = document.getElementById('btnBack2');
  if (btnBack2) btnBack2.addEventListener('click', () => showStep(1));
  const btnBack3 = document.getElementById('btnBack3');
  if (btnBack3) btnBack3.addEventListener('click', () => showStep(2));
  const btnBack4 = document.getElementById('btnBack4');
  if (btnBack4) btnBack4.addEventListener('click', () => showStep(3));

  // Final submit
  const btnSubmit = document.getElementById('btnSubmit');
  if (btnSubmit) {
    btnSubmit.addEventListener('click', function () {
      const q3 = document.getElementById('q3').value.trim();
      if (q3.length < 20) { showAlert('Please share your thoughts on applying this concept.'); return; }
      btnSubmit.disabled = true;
      btnSubmit.textContent = 'Submitting…';
      form.submit();
    });
  }

  function showLoading(visible) {
    const el = document.querySelector('.loading-state');
    const inner = document.querySelector('#panel2 .form-inner');
    if (!el || !inner) return;
    el.classList.toggle('visible', visible);
    inner.style.display = visible ? 'none' : 'block';
  }

  function showAlert(msg) {
    removeAlert();
    const el = document.createElement('div');
    el.id = 'formAlert';
    el.className = 'alert alert-error';
    el.textContent = msg;
    const activePanel = document.querySelector('.form-panel.active');
    if (activePanel) activePanel.prepend(el);
    setTimeout(removeAlert, 5000);
  }

  function removeAlert() {
    const el = document.getElementById('formAlert');
    if (el) el.remove();
  }

  showStep(1);
})();
