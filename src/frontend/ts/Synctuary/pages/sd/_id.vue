<template>
    <div>
      <h1>{{ sdCard.path }}</h1>
      <p>Total: {{ sdCard.total }}</p>
      <p>Used: {{ sdCard.used }}</p>
      <p>Free: {{ sdCard.free }}</p>
      <p>Number of Files: {{ sdCard.num_files }}</p>
      <p>Number of Directories: {{ sdCard.num_dirs }}</p>
      <v-btn @click="copySdCard">Copy</v-btn>
    </div>
  </template>

  <script>
  export default {
    async asyncData({ $axios, params }) {
      const sdCard = await $axios.$get(`/api/sd-cards/${params.id}/`)
      return { sdCard }
    },
    methods: {
      async copySdCard() {
        await this.$axios.$post(`/api/sd-cards/${this.sdCard.path}/copy/`)
        this.$router.push('/sd-cards/')
      },
    },
  }
  </script>
