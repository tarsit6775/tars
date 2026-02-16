let notificationsEnabled = false

export async function requestNotificationPermission(): Promise<boolean> {
  if (!('Notification' in window)) return false
  if (Notification.permission === 'granted') {
    notificationsEnabled = true
    return true
  }
  if (Notification.permission !== 'denied') {
    const perm = await Notification.requestPermission()
    notificationsEnabled = perm === 'granted'
    return notificationsEnabled
  }
  return false
}

export function sendBrowserNotification(title: string, body: string) {
  if (!notificationsEnabled) return
  if (document.hasFocus()) return // Don't notify if tab is focused
  try {
    new Notification(title, {
      body,
      icon: '/tars-icon.png',
      tag: 'tars-' + Date.now(),
    })
  } catch {
    // Notifications not supported
  }
}
