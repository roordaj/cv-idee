import { useState, type ReactNode } from 'react';
import { OnboardingContext } from './progress';
export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [step, setStep] = useState(1);
  return (
    <OnboardingContext.Provider value={{ step, setStep }}>{children}</OnboardingContext.Provider>
  );
}
