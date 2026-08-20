import receivedNowSnapshot from "../../../contracts/v2/fixtures/snapshot-received-now.valid.json";
import generatedManifest from "../../../public/models/conjunto-motor-bomba.manifest.json";


export const realSnapshot = receivedNowSnapshot;
export const normalSnapshot = {
  ...receivedNowSnapshot,
  status: "normal",
};
export const alertSnapshot = {
  ...receivedNowSnapshot,
  status: "alert",
};
export const realManifestFixture = generatedManifest;
