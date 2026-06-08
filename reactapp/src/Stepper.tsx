// reactapp/src/Stepper.tsx
import { Fragment } from 'react';
import { STEP_ORDER, STEP_LABELS, type Step } from './types';

interface StepperProps {
  current: Step;
}

function Stepper({ current }: StepperProps) {
  const currentIndex = STEP_ORDER.indexOf(current);

  return (
    <div className="stepper">
      {STEP_ORDER.map((stepId, i) => {
        const state =
          i < currentIndex ? 'complete' : i === currentIndex ? 'active' : 'pending';
        return (
          <Fragment key={stepId}>
            {i > 0 && (
              <div className={`stepper-line ${i <= currentIndex ? 'filled' : ''}`} />
            )}
            <div className="stepper-step">
              <div className={`stepper-circle ${state}`}>
                {state === 'complete' ? '✓' : i + 1}
              </div>
              <span className={`stepper-label ${state}`}>{STEP_LABELS[stepId]}</span>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}

export default Stepper;
