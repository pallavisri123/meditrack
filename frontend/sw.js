/* MediTrack service worker — shows real push notifications on the device,
   even when the MediTrack tab/app isn't open. */
self.addEventListener("push", (event) => {
  let data = { title: "MediTrack", body: "You have a new update.", url: "/dashboard.html" };
  try { if (event.data) data = { ...data, ...event.data.json() }; } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "https://cdn-icons-png.flaticon.com/512/2966/2966327.png",
      badge: "https://cdn-icons-png.flaticon.com/512/2966/2966327.png",
      data: { url: data.url || "/dashboard.html" },
      tag: "meditrack-notification",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/dashboard.html";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) { if (c.url.includes(url) && "focus" in c) return c.focus(); }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
