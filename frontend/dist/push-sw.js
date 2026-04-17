// Push notification handler — imported into the Workbox-generated SW
// via importScripts in vite.config.ts

self.addEventListener('push', function (event) {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: 'Broker Freund', body: event.data.text() };
  }

  const title = payload.title || 'Broker Freund';
  const options = {
    body: payload.body || '',
    icon: payload.icon || '/vite.svg',
    badge: '/icons/icon-192.png',
    tag: payload.tag || 'broker-freund',
    renotify: true,
    data: {
      url: payload.url || '/',
      ...(payload.data || {}),
    },
    actions: [
      { action: 'open', title: 'Open' },
      { action: 'dismiss', title: 'Dismiss' },
    ],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const url = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      // Focus existing window if available
      for (var i = 0; i < clientList.length; i++) {
        var client = clientList[i];
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.focus();
          if (url !== '/') client.navigate(url);
          return;
        }
      }
      // Otherwise open new window
      return clients.openWindow(url);
    })
  );
});
