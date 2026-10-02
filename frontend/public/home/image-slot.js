/**
 * Minimal image-slot custom element shim.
 * Renders the `src` attribute as a full-cover image inside the element.
 */
class ImageSlot extends HTMLElement {
  connectedCallback() {
    const src = this.getAttribute('src') || '';
    const fit = this.getAttribute('fit') || 'cover';
    const shape = this.getAttribute('shape') || 'rect';
    if (!src) return;
    this.style.display = 'block';
    this.style.overflow = 'hidden';
    if (shape === 'circle') this.style.borderRadius = '50%';
    const img = document.createElement('img');
    img.src = src;
    img.alt = this.getAttribute('placeholder') || '';
    img.style.cssText = `width:100%;height:100%;object-fit:${fit};display:block;`;
    img.onerror = () => { img.style.display = 'none'; };
    this.innerHTML = '';
    this.appendChild(img);
  }
}
customElements.define('image-slot', ImageSlot);
