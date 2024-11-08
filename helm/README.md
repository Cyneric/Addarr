# Helm Chart for Addarr

This Helm chart deploys Addarr, a Telegram bot for media management through Radarr, Sonarr, and Lidarr, on Kubernetes.

## Prerequisites

- Kubernetes 1.16+
- Helm 3.0+
- A StorageClass capable of provisioning PersistentVolumes
- A configured `config.yaml` file

## Installation

### Quick Install

1. Add the Helm repository:
```bash
helm repo add addarr https://cyneric.github.io/addarr
helm repo update
```

2. Install the chart:
```bash
helm install addarr addarr/addarr
```

### Custom Installation

1. Clone the repository:
```bash
git clone https://github.com/cyneric/addarr.git
cd addarr/helm
```

2. Edit the values in `values.yaml` to match your environment:
```yaml
image:
  repository: cyneric/addarr
  tag: latest
  pullPolicy: Always

config:
  # Your config.yaml contents here
  telegram:
    token: "your-bot-token"
  # ... rest of your configuration

persistence:
  enabled: true
  storageClass: "default"
  size: 1Gi

resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "200m"
```

3. Install the chart:
```bash
# Install in default namespace
helm upgrade -i addarr . -f values.yaml

# Or install in specific namespace
helm upgrade -i --namespace addarr --create-namespace addarr . -f values.yaml
```

## Configuration

### Important Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Docker image repository | `cyneric/addarr` |
| `image.tag` | Docker image tag | `latest` |
| `image.pullPolicy` | Image pull policy | `Always` |
| `persistence.enabled` | Enable persistent storage | `true` |
| `persistence.storageClass` | StorageClass for PVC | `""` |
| `persistence.size` | Size of persistent volume | `1Gi` |
| `resources` | Pod resource requests/limits | `{}` |
| `nodeSelector` | Node selector for pod assignment | `{}` |
| `tolerations` | Pod tolerations | `[]` |
| `affinity` | Pod affinity rules | `{}` |

### Configuration File

You can provide your configuration in two ways:

1. Through `values.yaml`:
```yaml
config:
  telegram:
    token: "your-bot-token"
  # ... rest of your configuration
```

2. Through an existing ConfigMap:
```yaml
configMap:
  name: "existing-config-map"
```

## Persistence

The chart mounts a PersistentVolume for storing logs and other persistent data. You can configure the storage using the `persistence` section in `values.yaml`.

## Upgrading

To upgrade an existing installation:

```bash
helm upgrade addarr . -f values.yaml
```

## Uninstalling

To remove the deployment:

```bash
helm uninstall addarr
```

Note: This will not remove the PersistentVolumeClaim. To remove it:
```bash
kubectl delete pvc -l app.kubernetes.io/name=addarr
```

## Troubleshooting

### Common Issues

1. **Pod won't start**
   - Check the pod logs: `kubectl logs -l app.kubernetes.io/name=addarr`
   - Verify config.yaml is correctly mounted
   - Ensure sufficient resources are available

2. **Storage issues**
   - Verify StorageClass exists and can provision volumes
   - Check PVC status: `kubectl get pvc`

3. **Configuration problems**
   - Verify ConfigMap contents: `kubectl get configmap addarr -o yaml`
   - Check for syntax errors in config.yaml

## Support

For issues and feature requests, please visit:
- [GitHub Issues](https://github.com/cyneric/addarr/issues)
- [Project Documentation](https://github.com/cyneric/addarr/wiki)