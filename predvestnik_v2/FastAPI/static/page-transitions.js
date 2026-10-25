// A cross-document transition can be cancelled when its destination does not opt in.
// Observe its visual promises on both pages before pagereveal; navigation itself succeeds.
(() => {
  for (const name of ['pageswap', 'pagereveal']) {
    addEventListener(name, event => {
      const transition = event.viewTransition;
      if (!transition) return;
      for (const promise of [transition.ready, transition.finished, transition.updateCallbackDone]) {
        promise?.catch(() => {});
      }
    });
  }
})();
