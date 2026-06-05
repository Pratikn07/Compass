import { Suspense } from "react";
import { LoadingState } from "@/components/states/loading-state";
import { DecisionListClient } from "@/features/decisions/decision-list-client";

export default function DecisionsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading decisions..." />}>
      <DecisionListClient />
    </Suspense>
  );
}
