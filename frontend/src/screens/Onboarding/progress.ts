import { createContext, useContext, useState } from 'react';
export const OnboardingContext = createContext<{
  step: number;
  setStep: (value: number) => void;
} | null>(null);
export const STEPS = ['Verbinding', 'Signalen koppelen', 'Historie importeren', 'Klaar'];
export function useOnboardingProgress() {
  const context = useContext(OnboardingContext);
  const [step, setStep] = useState(1);
  return context ?? { step, setStep };
}
