import { DecisionChainClient } from "@/features/decisions/decision-chain-client";

export default async function DecisionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return <DecisionChainClient decisionId={id} />;
}
