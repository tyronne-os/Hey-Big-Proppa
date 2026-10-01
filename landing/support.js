/**
 * Minimal Klarden Design Canvas runtime shim.
 * Powers: x-dc, helmet, sc-for, {{ mustache }} templates, DCLogic base class.
 */
(function() {
  // --- DCLogic base class ---
  window.DCLogic = class DCLogic {
    constructor() { this.state = {}; }
    setState(fn) {
      const next = typeof fn === 'function' ? fn(this.state) : fn;
      this.state = { ...this.state, ...next };
      if (this._root) this._render();
    }
    componentDidMount() {}
    componentWillUnmount() {}
    renderVals() { return {}; }
    _render() {
      if (!this._root) return;
      const vals = this.renderVals();
      _applyTemplates(this._root, vals);
    }
  };

  // --- Template interpolation ---
  function _interp(str, ctx) {
    return String(str).replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key) => {
      const val = key.split('.').reduce((o, k) => (o != null ? o[k] : ''), ctx);
      return val != null ? val : '';
    });
  }

  function _applyTemplates(root, ctx) {
    // Process sc-for loops
    root.querySelectorAll('sc-for[data-dc-rendered]').forEach(el => el.remove());
    root.querySelectorAll('sc-for:not([data-dc-rendered])').forEach(el => {
      const listKey = el.getAttribute('list') || '';
      const as = el.getAttribute('as') || 'item';
      const listMatch = listKey.match(/\{\{\s*([\w.]+)\s*\}\}/);
      if (!listMatch) return;
      const list = listMatch[1].split('.').reduce((o, k) => (o != null ? o[k] : null), ctx);
      if (!Array.isArray(list)) return;
      const tpl = el.innerHTML;
      const frag = document.createDocumentFragment();
      list.forEach(item => {
        const div = document.createElement('div');
        div.setAttribute('data-dc-rendered', '');
        div.style.cssText = el.style.cssText;
        const itemCtx = { ...ctx, [as]: item };
        div.innerHTML = _interp(tpl, itemCtx);
        frag.appendChild(div);
      });
      el.parentNode.insertBefore(frag, el.nextSibling);
      el.style.display = 'none';
    });

    // Interpolate text nodes
    _walkText(root, ctx);
  }

  function _walkText(node, ctx) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (node.textContent.includes('{{')) {
        node.textContent = _interp(node.textContent, ctx);
      }
      return;
    }
    if (node.nodeType === Node.ELEMENT_NODE) {
      // Interpolate attributes
      Array.from(node.attributes || []).forEach(attr => {
        if (attr.value.includes('{{')) {
          attr.value = _interp(attr.value, ctx);
        }
      });
    }
    node.childNodes.forEach(child => _walkText(child, ctx));
  }

  // --- x-dc custom element ---
  class XDC extends HTMLElement {
    connectedCallback() {
      // Process helmet (inject head tags)
      const helmet = this.querySelector('helmet');
      if (helmet) {
        helmet.childNodes.forEach(n => {
          if (n.nodeType === Node.ELEMENT_NODE) {
            document.head.appendChild(n.cloneNode(true));
          }
        });
        helmet.remove();
      }

      // Defer until DOMContentLoaded — the text/x-dc script is after </x-dc>
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => this._init(), { once: true });
      } else {
        setTimeout(() => this._init(), 0);
      }
    }
    _init() {
      const scriptEl = document.querySelector('script[type="text/x-dc"]');
      if (!scriptEl) return;
      try {
        const fn = new Function('DCLogic', scriptEl.textContent + '\nreturn Component;');
        const ComponentClass = fn(window.DCLogic);
        const inst = new ComponentClass();
        inst._root = this;
        inst.componentDidMount();
        inst._render();
        this._inst = inst;
      } catch(e) {
        console.warn('DC script error:', e);
      }
    }
    disconnectedCallback() {
      if (this._inst) this._inst.componentWillUnmount();
    }
  }
  customElements.define('x-dc', XDC);

  // sc-for element (placeholder, processed by _applyTemplates)
  class ScFor extends HTMLElement {}
  if (!customElements.get('sc-for')) customElements.define('sc-for', ScFor);
})();
