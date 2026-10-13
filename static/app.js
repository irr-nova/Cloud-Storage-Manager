const picker = document.getElementById('file-picker');
const uploadButton = document.getElementById('upload-button');
if (picker && uploadButton) {
  uploadButton.addEventListener('click', () => picker.click());
  picker.addEventListener('change', () => { if (picker.files.length) picker.form.submit(); });
}
document.querySelectorAll('.toast').forEach((toast) => {
  window.setTimeout(() => { toast.classList.add('hide'); }, 3600);
});
