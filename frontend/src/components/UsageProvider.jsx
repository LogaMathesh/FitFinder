import React, { useMemo } from 'react';
import { UsageContext, useUsageStore } from '../lib/usage';

// Holds the rate-limit credits for the signed-in user. Mount it with
// key={user} so logging in as someone else starts from that user's values.
export default function UsageProvider({ user, children }) {
  const { usage, now, pending, applyUsage } = useUsageStore(user);
  const value = useMemo(
    () => ({ usage, now, pending, applyUsage }),
    [usage, now, pending, applyUsage]
  );
  return <UsageContext.Provider value={value}>{children}</UsageContext.Provider>;
}
